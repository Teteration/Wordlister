"""Core APIs for building target-specific wordlists."""

from wordlister_core.errors import FetchError, InvalidTargetError, WordlisterError
from wordlister_core.models import (
    DiscoveryOptions,
    ExtractOptions,
    HttpOptions,
    WordInfo,
    WordlistResult,
)
from wordlister_core.pipeline import build_wordlist

__all__ = [
    "DiscoveryOptions",
    "ExtractOptions",
    "FetchError",
    "HttpOptions",
    "InvalidTargetError",
    "WordlistResult",
    "WordInfo",
    "WordlisterError",
    "build_wordlist",
]
