"""Extract backend-oriented paths and parameter names from HTTP URLs."""

from urllib.parse import parse_qsl, unquote, urljoin, urlparse

from wordlister_core.evidence import WordEvidence
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

MAX_NESTED_URL_DEPTH = 2


def extract_url(url: str, *, source: str | None = None, _depth: int = 0) -> WordEvidence:
    """Extract route segments, query names, and nested URL routes."""

    words = WordEvidence()
    parsed = urlparse(url)

    for segment in parsed.path.split("/"):
        if segment:
            words.add(tokenize(unquote(segment)), source or "url.path")

    for name, raw_value in parse_qsl(parsed.query, keep_blank_values=True):
        decoded_name = unquote(name)
        words.add(tokenize(decoded_name), source or "url.query.name")
        if not raw_value or is_sensitive_name(decoded_name):
            continue

        value = unquote(raw_value)
        if is_opaque_value(value):
            continue
        if _depth < MAX_NESTED_URL_DEPTH and (
            value.startswith(("http://", "https://", "/", "./", "../"))
        ):
            words.update(
                extract_url(
                    urljoin(url, value),
                    source=source or "url.query.url",
                    _depth=_depth + 1,
                )
            )

    return words
