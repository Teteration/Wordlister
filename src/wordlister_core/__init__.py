"""Core APIs for building target-specific wordlists."""

from wordlister_core.errors import FetchError, InvalidTargetError, WordlisterError
from wordlister_core.models import ExtractOptions, HttpOptions, WordlistResult
from wordlister_core.pipeline import build_wordlist

__all__ = [
    "ExtractOptions",
    "FetchError",
    "HttpOptions",
    "InvalidTargetError",
    "WordlistResult",
    "WordlisterError",
    "build_wordlist",
]
