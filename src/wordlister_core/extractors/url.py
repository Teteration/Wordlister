"""Extract target-specific candidates from HTTP URLs."""

from urllib.parse import parse_qsl, unquote, urljoin, urlparse

from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

MAX_NESTED_URL_DEPTH = 2


def extract_url(url: str, *, _depth: int = 0) -> set[str]:
    """Extract host, path, query, and fragment identifiers from a URL."""

    words: set[str] = set()
    parsed = urlparse(url)

    if parsed.hostname:
        for label in parsed.hostname.split("."):
            words.update(tokenize(unquote(label)))

    for segment in parsed.path.split("/"):
        if segment:
            words.update(tokenize(unquote(segment)))

    for name, raw_value in parse_qsl(parsed.query, keep_blank_values=True):
        decoded_name = unquote(name)
        words.update(tokenize(decoded_name))
        if not raw_value or is_sensitive_name(decoded_name):
            continue

        value = unquote(raw_value)
        if is_opaque_value(value):
            continue
        if _depth < MAX_NESTED_URL_DEPTH and (
            value.startswith(("http://", "https://", "/", "./", "../"))
        ):
            words.update(extract_url(urljoin(url, value), _depth=_depth + 1))
        else:
            words.update(tokenize(value))

    if parsed.fragment:
        words.update(tokenize(unquote(parsed.fragment)))

    return words
