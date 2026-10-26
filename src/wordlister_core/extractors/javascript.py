"""Best-effort extraction from JavaScript without executing target code."""

import re

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

DECLARATION_PATTERN = re.compile(
    r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(['\"])(.*?)\2",
    re.DOTALL,
)
REQUEST_PATTERN = re.compile(
    r"\b(fetch|import|axios\.(?:get|post|put|patch|delete)|(?:[A-Za-z_$][\w$]*\.)?open)"
    r"\s*\(\s*(['\"])(.*?)\2",
    re.DOTALL,
)
OBJECT_KEY_PATTERN = re.compile(r"(?:^|[{,])\s*([A-Za-z_$][\w$]*)\s*:", re.MULTILINE)


def _extract_value(value: str, base_url: str, source: str) -> WordEvidence:
    if not value or is_opaque_value(value):
        return WordEvidence()
    if value.startswith(("http://", "https://", "/", "./", "../")):
        from urllib.parse import urljoin

        return extract_url(urljoin(base_url, value), source=source)
    words = WordEvidence()
    words.add(tokenize(value), source)
    return words


def extract_javascript(source: str, *, base_url: str = "") -> WordEvidence:
    """Extract declaration names, safe string values, request URLs, and object keys."""

    words = WordEvidence()
    for match in DECLARATION_PATTERN.finditer(source):
        name, value = match.group(1), match.group(3)
        words.add(tokenize(name), "javascript.declaration")
        if not is_sensitive_name(name):
            words.update(_extract_value(value, base_url, "javascript.string"))

    for match in REQUEST_PATTERN.finditer(source):
        request_kind = match.group(1)
        if request_kind.endswith(".open") or request_kind == "open":
            request_source = "javascript.xhr.open"
        else:
            request_source = f"javascript.{request_kind}"
        words.update(_extract_value(match.group(3), base_url, request_source))

    for match in OBJECT_KEY_PATTERN.finditer(source):
        words.add(tokenize(match.group(1)), "javascript.object_key")

    return words
