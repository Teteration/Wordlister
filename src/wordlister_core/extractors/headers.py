"""Extract safe candidates from selected HTTP response headers."""

import re
from collections.abc import Mapping
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urljoin

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import tokenize

URL_HEADERS = {"content-location", "location", "refresh"}
TOKEN_LIST_HEADERS = {
    "access-control-allow-headers",
    "access-control-expose-headers",
    "allow",
}
FILENAME_PATTERN = re.compile(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", re.IGNORECASE)
REFRESH_URL_PATTERN = re.compile(r"(?:^|;)\s*url\s*=\s*(.+)$", re.IGNORECASE)


def _extract_set_cookie(value: str, base_url: str) -> WordEvidence:
    words = WordEvidence()
    cookie = SimpleCookie()
    try:
        cookie.load(value)
    except CookieError:
        return words

    for morsel in cookie.values():
        words.add(tokenize(morsel.key), "header.cookie.name")
        if morsel["path"]:
            words.update(
                extract_url(urljoin(base_url, morsel["path"]), source="header.cookie.path")
            )
        if morsel["domain"]:
            words.add(tokenize(morsel["domain"]), "header.cookie.domain")
    return words


def extract_headers(headers: Mapping[str, str], base_url: str) -> WordEvidence:
    """Extract header names and allowlisted non-secret values."""

    words = WordEvidence()
    for name, value in headers.items():
        lower_name = name.lower()
        words.add(tokenize(name), "header.name")

        if lower_name == "set-cookie":
            words.update(_extract_set_cookie(value, base_url))
        elif lower_name in URL_HEADERS:
            candidate = value
            if lower_name == "refresh":
                match = REFRESH_URL_PATTERN.search(value)
                if not match:
                    continue
                candidate = match.group(1).strip(" '\"")
            words.update(extract_url(urljoin(base_url, candidate), source="header.location"))
        elif lower_name == "content-disposition":
            match = FILENAME_PATTERN.search(value)
            if match:
                words.add(tokenize(match.group(1)), "header.filename")
        elif lower_name in TOKEN_LIST_HEADERS:
            for item in value.split(","):
                words.add(tokenize(item.strip()), "header.value")

    return words
