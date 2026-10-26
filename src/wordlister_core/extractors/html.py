"""Extract candidates from HTML without executing embedded content."""

from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.javascript import extract_javascript
from wordlister_core.extractors.json_data import extract_json_text
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, tokenize

FORM_FIELD_TAGS = {"button", "input", "select", "textarea"}
ENDPOINT_ATTRIBUTES: dict[str, set[str] | None] = {
    "action": {"form"},
    "formaction": {"button", "input"},
    "href": {"a", "area"},
    "src": {"frame", "iframe"},
    "data-api": None,
    "data-endpoint": None,
    "data-href": None,
    "data-url": None,
}


def _attribute_values(value: object) -> Iterable[str]:
    if isinstance(value, list):
        return (str(item) for item in value)
    return (str(value),)


def _is_endpoint_reference(value: str) -> bool:
    """Reject browser-only and non-HTTP link schemes before URL extraction."""

    lowered = value.strip().lower()
    return bool(lowered) and not lowered.startswith(
        ("#", "data:", "javascript:", "mailto:", "tel:")
    )


def extract_html(
    html: str,
    base_url: str,
    *,
    include_comments: bool = False,
) -> WordEvidence:
    """Extract backend input names and endpoint references from HTML."""

    soup = BeautifulSoup(html, "html.parser")
    words = WordEvidence()

    for tag in soup.find_all(True):
        if tag.name in FORM_FIELD_TAGS and "name" in tag.attrs:
            for value in _attribute_values(tag.attrs["name"]):
                if value and not is_opaque_value(value):
                    words.add(tokenize(value), "form.field.name")

        for name, raw_value in tag.attrs.items():
            allowed_tags = ENDPOINT_ATTRIBUTES.get(name, set())
            if allowed_tags == set() or (allowed_tags is not None and tag.name not in allowed_tags):
                continue
            for value in _attribute_values(raw_value):
                if not _is_endpoint_reference(value) or is_opaque_value(value):
                    continue
                source = (
                    "form.action" if tag.name == "form" and name == "action" else f"html.{name}"
                )
                words.update(extract_url(urljoin(base_url, value), source=source))

    for script in soup.find_all("script"):
        source = script.string or script.get_text()
        if not source:
            continue
        script_type = str(script.attrs.get("type", "")).lower()
        if "json" in script_type:
            words.update(extract_json_text(source, base_url=base_url))
        else:
            words.update(extract_javascript(source, base_url=base_url))

    if include_comments:
        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            words.add(tokenize(str(comment)), "html.comment")

    return words
