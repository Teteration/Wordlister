"""Typed data passed between Wordlister's modules."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ExtractOptions:
    """Controls final word filtering without coupling core code to argparse."""

    min_length: int = 1
    max_length: int = 100
    character_filter: Literal["ascii", "unicode"] = "unicode"
    drop_obfuscated: bool = False
    include_comments: bool = False

    def __post_init__(self) -> None:
        if self.min_length < 1:
            raise ValueError("min_length must be at least 1")
        if self.max_length < self.min_length:
            raise ValueError("max_length must be greater than or equal to min_length")


@dataclass(frozen=True, slots=True)
class DiscoveryOptions:
    """Controls optional URL discovery by an external crawler."""

    provider: Literal["none", "hakrawler"] = "none"
    mode: Literal["single", "domain", "subdomain"] = "domain"
    max_depth: int = 0
    max_pages: int = 1000
    timeout: int = 120
    executable: str = "hakrawler"

    def __post_init__(self) -> None:
        if self.provider not in {"none", "hakrawler"}:
            raise ValueError("unsupported crawler provider")
        if self.mode not in {"single", "domain", "subdomain"}:
            raise ValueError("unsupported crawler mode")
        if self.max_depth < 0:
            raise ValueError("depth cannot be negative")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if self.timeout < 1:
            raise ValueError("crawler_timeout must be at least 1 second")
        if not self.executable or "\x00" in self.executable:
            raise ValueError("crawler_path must name an executable")
        if self.provider == "none" and self.max_depth > 0:
            raise ValueError("--depth requires --crawler hakrawler")


@dataclass(frozen=True, slots=True)
class HttpOptions:
    """Safety and resource limits for HTTP requests."""

    connect_timeout: float = 3.05
    read_timeout: float = 10.0
    max_response_bytes: int = 2 * 1024 * 1024
    max_redirects: int = 5
    max_url_length: int = 8 * 1024
    user_agent: str = "wordlister/0.2 (+https://github.com/Teteration/Wordlister)"

    def __post_init__(self) -> None:
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("HTTP timeouts must be greater than zero")
        if self.max_response_bytes < 1:
            raise ValueError("max_response_bytes must be at least 1")
        if self.max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        if self.max_url_length < 1:
            raise ValueError("max_url_length must be at least 1")


@dataclass(frozen=True, slots=True)
class RedirectHop:
    """Metadata retained from one redirect response."""

    url: str
    status_code: int
    headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class FetchedResponse:
    """A size-bounded response detached from the requests library."""

    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    history: tuple[RedirectHop, ...]
    text: str


@dataclass(frozen=True, slots=True)
class TargetFailure:
    """A deterministic, sanitized failure associated with one input target."""

    target: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class WordInfo:
    """A word's occurrence count, source-based score, and provenance labels."""

    word: str
    count: int
    score: int
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WordlistResult:
    """Aggregated words and failures for a single pipeline run."""

    words: tuple[str, ...]
    failures: tuple[TargetFailure, ...]
    processed_targets: int
    entries: tuple[WordInfo, ...] = ()
