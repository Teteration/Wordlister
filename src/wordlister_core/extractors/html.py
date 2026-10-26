"""Extract candidates from HTML without executing embedded content."""

from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, Tag

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.javascript import extract_javascript
from wordlister_core.extractors.json_data import extract_json_text
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

URL_ATTRIBUTES = {
    "action",
    "data",
    "data-api",
    "data-endpoint",
    "data-href",
    "data-src",
    "data-url",
    "formaction",
    "href",
    "poster",
    "src",
}
SKIPPED_VALUE_ATTRIBUTES = {"integrity", "nonce", "style"}


def _attribute_values(value: object) -> Iterable[str]:
    if isinstance(value, list):
        return (str(item) for item in value)
    return (str(value),)


def _extract_srcset(value: str, base_url: str) -> WordEvidence:
    words = WordEvidence()
    for entry in value.split(","):
        candidate = entry.strip().split(maxsplit=1)[0]
        if candidate:
            words.update(extract_url(urljoin(base_url, candidate), source="html.srcset"))
    return words


def _tag_has_sensitive_value(tag: Tag) -> bool:
    field_name = str(tag.attrs.get("name", ""))
    field_type = str(tag.attrs.get("type", ""))
    return field_type.lower() in {"password", "hidden"} or is_sensitive_name(field_name)


def extract_html(html: str, base_url: str, *, include_comments: bool = False) -> WordEvidence:
    """Extract visible text, attributes, linked URLs, JSON, JS, and optional comments."""

    soup = BeautifulSoup(html, "html.parser")
    text_soup = BeautifulSoup(html, "html.parser")
    for element in text_soup(["script", "style"]):
        element.extract()
    words = WordEvidence()
    words.add(tokenize(text_soup.get_text(" ", strip=True)), "html.text")

    for tag in soup.find_all(True):
        sensitive_value = _tag_has_sensitive_value(tag)
        for name, raw_value in tag.attrs.items():
            words.add(tokenize(name), "html.attribute.name")
            if name in SKIPPED_VALUE_ATTRIBUTES:
                continue
            for value in _attribute_values(raw_value):
                if not value or is_opaque_value(value):
                    continue
                if name == "value" and sensitive_value:
                    continue
                if is_sensitive_name(name):
                    continue
                if name == "srcset":
                    words.update(_extract_srcset(value, base_url))
                elif name in URL_ATTRIBUTES:
                    source = (
                        "form.action" if tag.name == "form" and name == "action" else f"html.{name}"
                    )
                    words.update(extract_url(urljoin(base_url, value), source=source))
                else:
                    words.add(tokenize(value), f"html.{name}")

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
