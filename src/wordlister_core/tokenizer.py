"""Turn target-derived text into useful identifier-aware word candidates."""

import math
import re
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wordlister_core.models import ExtractOptions

LEXEME_PATTERN = re.compile(r"[^\W]+(?:[-.][^\W]+)*", re.UNICODE)
IDENTIFIER_PART_PATTERN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|\d+")
SEPARATOR_PATTERN = re.compile(r"[_\-.:/\\]+")
JWT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$")
HEX_PATTERN = re.compile(r"^[A-Fa-f0-9]{16,}$")

SENSITIVE_COMPONENTS = {
    "apikey",
    "authorization",
    "auth",
    "credential",
    "credentials",
    "csrf",
    "jwt",
    "passwd",
    "password",
    "privatekey",
    "secret",
    "sessionid",
    "token",
    "xsrf",
}


def _identifier_parts(value: str) -> list[str]:
    parts: list[str] = []
    for chunk in filter(None, SEPARATOR_PATTERN.split(value)):
        chunk_parts = IDENTIFIER_PART_PATTERN.findall(chunk)
        index = 0
        while index < len(chunk_parts):
            current = chunk_parts[index]
            if (
                len(current) == 1
                and current.isupper()
                and index + 1 < len(chunk_parts)
                and chunk_parts[index + 1].isdigit()
            ):
                parts.append(current + chunk_parts[index + 1])
                index += 2
                continue
            parts.append(current)
            index += 1
    return parts


def tokenize(text: str) -> Counter[str]:
    """Count original lexemes and identifier components once per occurrence."""

    words: Counter[str] = Counter()
    for match in LEXEME_PATTERN.finditer(text):
        lexeme = match.group(0)
        occurrence = {lexeme}
        occurrence.update(part for part in _identifier_parts(lexeme) if part)
        if "." in lexeme:
            stem = lexeme.rsplit(".", maxsplit=1)[0]
            if stem:
                occurrence.add(stem)
                occurrence.update(part for part in _identifier_parts(stem) if part)
        words.update(occurrence)
    return words


def is_sensitive_name(name: str) -> bool:
    """Return whether a key/name indicates that its associated value is sensitive."""

    normalized = "".join(_identifier_parts(name)).lower()
    components = {part.lower() for part in _identifier_parts(name)}
    return normalized in SENSITIVE_COMPONENTS or bool(components & SENSITIVE_COMPONENTS)


def _shannon_entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def is_opaque_value(value: str) -> bool:
    """Detect common secret/token shapes that should not become wordlist entries."""

    stripped = value.strip()
    if "BEGIN PRIVATE KEY" in stripped or "BEGIN RSA PRIVATE KEY" in stripped:
        return True
    if JWT_PATTERN.fullmatch(stripped) or HEX_PATTERN.fullmatch(stripped):
        return True
    if stripped.startswith(("ghp_", "github_pat_", "sk_live_", "sk_test_")):
        return True
    compact = re.sub(r"\s+", "", stripped)
    return (
        len(compact) >= 32
        and any(character.isalpha() for character in compact)
        and any(character.isdigit() for character in compact)
        and _shannon_entropy(compact) >= 4.0
    )


def _is_ascii(value: str) -> bool:
    return value.isascii()


def _is_obfuscated_hex(value: str) -> bool:
    if len(value) < 6:
        return False
    hexadecimal = sum(character.upper() in "0123456789ABCDEF" for character in value)
    return hexadecimal / len(value) > 0.8


def filter_words(words: Iterable[str], options: "ExtractOptions") -> set[str]:
    """Apply deterministic output filters after source-specific extraction."""

    from wordlister_core.models import ExtractOptions

    if not isinstance(options, ExtractOptions):
        raise TypeError("options must be an ExtractOptions instance")

    filtered: set[str] = set()
    for word in words:
        if word.isdigit() or not options.min_length <= len(word) <= options.max_length:
            continue
        if options.character_filter == "ascii" and not _is_ascii(word):
            continue
        if options.drop_obfuscated and _is_obfuscated_hex(word):
            continue
        if is_opaque_value(word):
            continue
        filtered.add(word)
    return filtered


def filter_word_counts(words: Counter[str], options: "ExtractOptions") -> Counter[str]:
    """Apply output filters while preserving occurrence counts."""

    allowed = filter_words(words, options)
    return Counter({word: count for word, count in words.items() if word in allowed})
