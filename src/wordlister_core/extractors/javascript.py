"""Best-effort extraction from JavaScript without executing target code."""

import re

from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

DECLARATION_PATTERN = re.compile(
    r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(['\"])(.*?)\2",
    re.DOTALL,
)
REQUEST_PATTERN = re.compile(
    r"\b(?:fetch|import|axios\.(?:get|post|put|patch|delete)|\.open)\s*\(\s*"
    r"(['\"])(.*?)\1",
    re.DOTALL,
)
OBJECT_KEY_PATTERN = re.compile(r"(?:^|[{,])\s*([A-Za-z_$][\w$]*)\s*:", re.MULTILINE)


def _extract_value(value: str, base_url: str) -> set[str]:
    if not value or is_opaque_value(value):
        return set()
    if value.startswith(("http://", "https://", "/", "./", "../")):
        from urllib.parse import urljoin

        return extract_url(urljoin(base_url, value))
    return tokenize(value)


def extract_javascript(source: str, *, base_url: str = "") -> set[str]:
    """Extract declaration names, safe string values, request URLs, and object keys."""

    words: set[str] = set()
    for match in DECLARATION_PATTERN.finditer(source):
        name, value = match.group(1), match.group(3)
        words.update(tokenize(name))
        if not is_sensitive_name(name):
            words.update(_extract_value(value, base_url))

    for match in REQUEST_PATTERN.finditer(source):
        words.update(_extract_value(match.group(2), base_url))

    for match in OBJECT_KEY_PATTERN.finditer(source):
        words.update(tokenize(match.group(1)))

    return words
