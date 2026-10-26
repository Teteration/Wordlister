"""Bounded recursive extraction from JSON documents."""

import json
from typing import Any

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.url import extract_url
from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize

MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000
MAX_STRING_LENGTH = 8 * 1024


def extract_json_text(text: str, *, base_url: str = "") -> WordEvidence:
    """Parse JSON and extract keys plus safe, human-meaningful string values."""

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return WordEvidence()

    words = WordEvidence()
    nodes_seen = 0

    def visit(value: Any, *, key: str | None = None, depth: int = 0) -> None:
        nonlocal nodes_seen
        if depth > MAX_JSON_DEPTH or nodes_seen >= MAX_JSON_NODES:
            return
        nodes_seen += 1

        if isinstance(value, dict):
            for child_key, child_value in value.items():
                key_text = str(child_key)
                words.add(tokenize(key_text), "json.key")
                visit(child_value, key=key_text, depth=depth + 1)
            return

        if isinstance(value, list):
            for item in value:
                visit(item, key=key, depth=depth + 1)
            return

        if not isinstance(value, str) or not value or len(value) > MAX_STRING_LENGTH:
            return
        if is_opaque_value(value):
            return
        if value.startswith(("http://", "https://", "/", "./", "../")):
            words.update(extract_url(urljoin_safe(base_url, value), source="json.url"))
        elif key and is_sensitive_name(key):
            return
        else:
            words.add(tokenize(value), "json.value")

    visit(payload)
    return words


def urljoin_safe(base_url: str, value: str) -> str:
    """Resolve relative JSON URL values without requiring a base URL."""

    if value.startswith(("http://", "https://")) or not base_url:
        return value
    from urllib.parse import urljoin

    return urljoin(base_url, value)
