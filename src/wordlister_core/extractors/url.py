"""Extract target-specific candidates from HTTP URLs."""

from urllib.parse import parse_qsl, unquote, urljoin, urlparse

from wordlister_core.evidence import WordEvidence
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

MAX_NESTED_URL_DEPTH = 2


def extract_url(url: str, *, source: str | None = None, _depth: int = 0) -> WordEvidence:
    """Extract host, path, query, and fragment identifiers from a URL."""

    words = WordEvidence()
    parsed = urlparse(url)

    if parsed.hostname:
        for label in parsed.hostname.split("."):
            words.add(tokenize(unquote(label)), source or "url.host")

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
                    source=source or "url.query.value",
                    _depth=_depth + 1,
                )
            )
        else:
            words.add(tokenize(value), source or "url.query.value")

    if parsed.fragment:
        words.add(tokenize(unquote(parsed.fragment)), source or "url.fragment")

    return words
