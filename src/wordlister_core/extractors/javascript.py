"""Best-effort extraction from JavaScript without executing target code."""

import re

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, tokenize

REQUEST_PATTERN = re.compile(
    r"\b(fetch|axios\.(?:get|post|put|patch|delete))"
    r"\s*\(\s*(['\"])(.*?)\2",
    re.DOTALL,
)
XHR_OPEN_PATTERN = re.compile(
    r"\b(?:[A-Za-z_$][\w$]*\.)?open\s*\(\s*(['\"])[A-Z]+\1\s*,\s*(['\"])(.*?)\2",
    re.IGNORECASE | re.DOTALL,
)
DECLARATION_URL_PATTERN = re.compile(
    r"\b(?:var|let|const)\s+[A-Za-z_$][\w$]*\s*=\s*(['\"])((?:https?://|/|\./|\.\./).*?)\1",
    re.DOTALL,
)
OBJECT_KEY_PATTERN = re.compile(r"(?:^|[{,])\s*(['\"]?)([A-Za-z_$][\w$.-]*)\1\s*:")
PARAMETER_CONTAINER_PATTERN = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*new\s+(?:FormData|URLSearchParams)\b"
)
JSON_PAYLOAD_PATTERN = re.compile(r"JSON\.stringify\s*\(\s*\{(.*?)\}\s*\)", re.DOTALL)
URL_SEARCH_PARAMS_PATTERN = re.compile(r"new\s+URLSearchParams\s*\(\s*\{(.*?)\}\s*\)", re.DOTALL)
AXIOS_PAYLOAD_PATTERN = re.compile(
    r"\baxios\.(?:post|put|patch)\s*\(\s*(['\"])(.*?)\1\s*,\s*\{(.*?)\}\s*\)",
    re.DOTALL,
)


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
    """Extract request URLs and likely backend parameter names."""

    words = WordEvidence()
    for match in DECLARATION_URL_PATTERN.finditer(source):
        words.update(_extract_value(match.group(2), base_url, "javascript.url"))

    for match in REQUEST_PATTERN.finditer(source):
        request_kind = match.group(1)
        words.update(_extract_value(match.group(3), base_url, f"javascript.{request_kind}"))

    for match in XHR_OPEN_PATTERN.finditer(source):
        words.update(_extract_value(match.group(3), base_url, "javascript.xhr.open"))

    payloads = [match.group(1) for match in JSON_PAYLOAD_PATTERN.finditer(source)]
    payloads.extend(match.group(1) for match in URL_SEARCH_PARAMS_PATTERN.finditer(source))
    payloads.extend(match.group(3) for match in AXIOS_PAYLOAD_PATTERN.finditer(source))
    for payload in payloads:
        for match in OBJECT_KEY_PATTERN.finditer("{" + payload):
            words.add(tokenize(match.group(2)), "javascript.parameter")

    for container_match in PARAMETER_CONTAINER_PATTERN.finditer(source):
        container = re.escape(container_match.group(1))
        method_pattern = re.compile(
            rf"\b{container}\.(?:append|set)\s*\(\s*(['\"])([A-Za-z_$][\w$.-]*)\1"
        )
        for match in method_pattern.finditer(source):
            words.add(tokenize(match.group(2)), "javascript.parameter")

    return words
