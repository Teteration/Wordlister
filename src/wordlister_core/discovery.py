"""Optional URL discovery through external crawler adapters."""

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import urlparse, urlunparse

from wordlister_core.errors import InvalidTargetError, WordlisterError
from wordlister_core.http import validate_http_url
from wordlister_core.models import DiscoveryOptions

MAX_CRAWLER_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_CRAWLER_ERROR_BYTES = 64 * 1024
PROXY_ENVIRONMENT_KEYS = {
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "proxy",
}
SKIPPED_ASSET_SUFFIXES = {
    ".7z",
    ".avi",
    ".avif",
    ".bmp",
    ".bz2",
    ".css",
    ".doc",
    ".docx",
    ".eot",
    ".flac",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".map",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".rar",
    ".svg",
    ".tar",
    ".tgz",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".zip",
}


@dataclass(frozen=True, slots=True)
class _ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class DiscoveryProvider(Protocol):
    """Provider boundary for producing untrusted candidate URLs from one seed."""

    def discover(
        self,
        seed: str,
        options: DiscoveryOptions,
        *,
        workers: int,
        max_url_length: int,
        max_response_bytes: int,
    ) -> tuple[str, ...]: ...


def normalize_discovered_url(url: str, *, max_length: int) -> str:
    """Validate and canonicalize one discovered URL for deterministic deduplication."""

    validate_http_url(url, max_length=max_length)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    netloc = (
        rendered_host if parsed.port in {None, default_port} else f"{rendered_host}:{parsed.port}"
    )
    return urlunparse((scheme, netloc, parsed.path or "/", parsed.params, parsed.query, ""))


def _effective_port(url: str) -> int:
    parsed = urlparse(url)
    return parsed.port or (443 if parsed.scheme.lower() == "https" else 80)


def _url_in_scope(url: str, seed: str, mode: str) -> bool:
    candidate = urlparse(url)
    root = urlparse(seed)
    candidate_host = (candidate.hostname or "").lower()
    root_host = (root.hostname or "").lower()

    if mode == "domain":
        host_allowed = candidate_host == root_host
    elif mode == "subdomain":
        try:
            ip_address(root_host)
            root_is_ip = True
        except ValueError:
            root_is_ip = False
        host_allowed = candidate_host == root_host or (
            not root_is_ip and candidate_host.endswith(f".{root_host}")
        )
    else:
        return url == seed
    if not host_allowed:
        return False

    candidate_scheme = candidate.scheme.lower()
    root_scheme = root.scheme.lower()
    if candidate_scheme == root_scheme:
        return _effective_port(url) == _effective_port(seed)
    return (
        root_scheme == "http"
        and candidate_scheme == "https"
        and _effective_port(seed) == 80
        and _effective_port(url) == 443
    )


def _is_asset_url(url: str) -> bool:
    return PurePosixPath(urlparse(url).path).suffix.lower() in SKIPPED_ASSET_SUFFIXES


def _safe_subprocess_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in PROXY_ENVIRONMENT_KEYS}


def _execute_hakrawler(command: list[str], seed: str, timeout: int) -> _ProcessResult:
    """Execute hakrawler without a shell while keeping captured output off the Python heap."""

    with (
        tempfile.TemporaryFile() as stdin_file,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        stdin_file.write(f"{seed}\n".encode())
        stdin_file.seek(0)
        try:
            process = subprocess.Popen(
                command,
                stdin=stdin_file,
                stdout=stdout_file,
                stderr=stderr_file,
                env=_safe_subprocess_environment(),
            )
        except FileNotFoundError as error:
            raise WordlisterError(
                "hakrawler executable was not found; install it with "
                "'go install github.com/hakluke/hakrawler@latest'"
            ) from error
        except OSError as error:
            raise WordlisterError("hakrawler could not be started") from error

        deadline = time.monotonic() + timeout + 5
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise WordlisterError("hakrawler exceeded the configured crawler timeout")
            if os.fstat(stdout_file.fileno()).st_size > MAX_CRAWLER_OUTPUT_BYTES:
                process.kill()
                process.wait()
                raise WordlisterError("hakrawler output exceeded the supported size limit")
            if os.fstat(stderr_file.fileno()).st_size > MAX_CRAWLER_ERROR_BYTES:
                process.kill()
                process.wait()
                raise WordlisterError(
                    "hakrawler diagnostic output exceeded the supported size limit"
                )
            time.sleep(0.05)

        stdout_size = os.fstat(stdout_file.fileno()).st_size
        if stdout_size > MAX_CRAWLER_OUTPUT_BYTES:
            raise WordlisterError("hakrawler output exceeded the supported size limit")
        stderr_size = os.fstat(stderr_file.fileno()).st_size
        if stderr_size > MAX_CRAWLER_ERROR_BYTES:
            raise WordlisterError("hakrawler diagnostic output exceeded the supported size limit")
        stdout_file.seek(0)
        stderr_file.seek(0)
        return _ProcessResult(
            returncode=process.returncode,
            stdout=stdout_file.read(MAX_CRAWLER_OUTPUT_BYTES),
            stderr=stderr_file.read(MAX_CRAWLER_ERROR_BYTES),
        )


def _hakrawler_command(
    options: DiscoveryOptions,
    *,
    workers: int,
    max_response_bytes: int,
) -> list[str]:
    command = [
        options.executable,
        "-json",
        "-u",
        "-d",
        str(options.max_depth),
        "-t",
        str(workers),
        "-timeout",
        str(options.timeout),
        "-size",
        str(max(1, (max_response_bytes + 1023) // 1024)),
        "-dr",
    ]
    if options.mode == "subdomain":
        command.append("-subs")
    return command


@dataclass(frozen=True, slots=True)
class HakrawlerDiscovery:
    """Discover URLs with hakrawler and independently enforce Wordlister policy."""

    def discover(
        self,
        seed: str,
        options: DiscoveryOptions,
        *,
        workers: int,
        max_url_length: int,
        max_response_bytes: int,
    ) -> tuple[str, ...]:
        result = _execute_hakrawler(
            _hakrawler_command(options, workers=workers, max_response_bytes=max_response_bytes),
            seed,
            options.timeout,
        )
        if result.returncode != 0:
            raise WordlisterError(f"hakrawler exited with status {result.returncode}")

        discovered: set[str] = set()
        records_seen = 0
        for raw_line in result.stdout.splitlines():
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            raw_url = item.get("URL") if isinstance(item, dict) else None
            if not isinstance(raw_url, str):
                continue
            records_seen += 1
            try:
                url = normalize_discovered_url(raw_url, max_length=max_url_length)
            except InvalidTargetError:
                continue
            if _url_in_scope(url, seed, options.mode) and not _is_asset_url(url):
                discovered.add(url)

        if result.stdout.strip() and records_seen == 0:
            raise WordlisterError("hakrawler returned an unsupported output format")
        return tuple(sorted(discovered))


def discover_targets(
    targets: Sequence[str],
    *,
    options: DiscoveryOptions,
    workers: int,
    max_url_length: int,
    max_response_bytes: int,
    provider: DiscoveryProvider | None = None,
) -> tuple[str, ...]:
    """Return validated seed URLs plus bounded targets discovered by the selected provider."""

    if workers < 1:
        raise ValueError("workers must be at least 1")

    stripped_targets = tuple(dict.fromkeys(target.strip() for target in targets if target.strip()))
    if options.provider == "none" or options.mode == "single" or options.max_depth == 0:
        return stripped_targets

    seeds = tuple(
        dict.fromkeys(
            normalize_discovered_url(target.strip(), max_length=max_url_length)
            for target in stripped_targets
        )
    )

    selected: list[str] = []
    active_provider = provider or HakrawlerDiscovery()
    for seed in seeds:
        discovered = active_provider.discover(
            seed,
            options,
            workers=workers,
            max_url_length=max_url_length,
            max_response_bytes=max_response_bytes,
        )
        per_seed = (seed, *(url for url in discovered if url != seed))[: options.max_pages]
        selected.extend(per_seed)
    return tuple(dict.fromkeys(selected))
