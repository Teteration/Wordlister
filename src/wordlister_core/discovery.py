"""Untrusted URL discovery through Burp history imports and Katana."""

import base64
import binascii
import json
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urljoin, urlparse, urlunparse

from wordlister_core.errors import InvalidTargetError, WordlisterError
from wordlister_core.http import validate_http_url
from wordlister_core.models import DiscoveryOptions

MAX_DISCOVERY_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_DISCOVERY_ERROR_BYTES = 64 * 1024
MAX_BURP_HISTORY_BYTES = 128 * 1024 * 1024
MAX_BURP_HISTORY_ITEMS = 1_000_000
MAX_BURP_REQUEST_BYTES = 2 * 1024 * 1024
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


def _katana_scope_pattern(seed: str, mode: str) -> str:
    parsed = urlparse(seed)
    hostname = parsed.hostname or ""
    host_pattern = re.escape(hostname)
    if mode == "subdomain":
        try:
            ip_address(hostname)
        except ValueError:
            host_pattern = rf"(?:[^/?#.]+\.)*{host_pattern}"

    scheme = parsed.scheme.lower()
    port = _effective_port(seed)
    if scheme == "http" and port == 80:
        origin_pattern = rf"(?:http://{host_pattern}(?::80)?|https://{host_pattern}(?::443)?)"
    elif (scheme, port) == ("https", 443):
        origin_pattern = rf"https://{host_pattern}(?::443)?"
    else:
        origin_pattern = rf"{re.escape(scheme)}://{host_pattern}:{port}"
    return rf"^{origin_pattern}(?:[/?#]|$)"


def _execute_katana(command: list[str], timeout: int) -> _ProcessResult:
    """Execute Katana without a shell and terminate it when resource limits are crossed."""

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=_safe_subprocess_environment(),
            )
        except FileNotFoundError as error:
            raise WordlisterError(
                "katana executable was not found; install it with "
                "'go install github.com/projectdiscovery/katana/cmd/katana@latest'"
            ) from error
        except OSError as error:
            raise WordlisterError("katana could not be started") from error

        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise WordlisterError("katana exceeded the configured crawler timeout")
            if os.fstat(stdout_file.fileno()).st_size > MAX_DISCOVERY_OUTPUT_BYTES:
                process.kill()
                process.wait()
                raise WordlisterError("katana output exceeded the supported size limit")
            if os.fstat(stderr_file.fileno()).st_size > MAX_DISCOVERY_ERROR_BYTES:
                process.kill()
                process.wait()
                raise WordlisterError("katana diagnostic output exceeded the supported size limit")
            time.sleep(0.05)

        stdout_size = os.fstat(stdout_file.fileno()).st_size
        stderr_size = os.fstat(stderr_file.fileno()).st_size
        if stdout_size > MAX_DISCOVERY_OUTPUT_BYTES:
            raise WordlisterError("katana output exceeded the supported size limit")
        if stderr_size > MAX_DISCOVERY_ERROR_BYTES:
            raise WordlisterError("katana diagnostic output exceeded the supported size limit")
        stdout_file.seek(0)
        stderr_file.seek(0)
        return _ProcessResult(
            returncode=process.returncode,
            stdout=stdout_file.read(MAX_DISCOVERY_OUTPUT_BYTES),
            stderr=stderr_file.read(MAX_DISCOVERY_ERROR_BYTES),
        )


def _katana_command(
    seed: str,
    options: DiscoveryOptions,
    *,
    workers: int,
    max_response_bytes: int,
) -> list[str]:
    command = [
        options.executable,
        "-u",
        seed,
        "-jsonl",
        "-omit-raw",
        "-omit-body",
        "-silent",
        "-no-color",
        "-disable-update-check",
        "-disable-redirects",
        "-ignore-query-params",
        "-strategy",
        "breadth-first",
        "-depth",
        str(options.max_depth),
        "-concurrency",
        str(workers),
        "-parallelism",
        "1",
        "-timeout",
        str(min(options.timeout, 60)),
        "-crawl-duration",
        f"{options.timeout}s",
        "-max-response-size",
        str(max_response_bytes),
        "-crawl-scope",
        _katana_scope_pattern(seed, options.mode),
    ]
    if options.js_crawl:
        command.append("-js-crawl")
    return command


def _katana_record_url(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    request = item.get("request")
    if isinstance(request, dict):
        endpoint = request.get("endpoint")
        if isinstance(endpoint, str):
            return endpoint
    for key in ("url", "endpoint"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return None


@dataclass(frozen=True, slots=True)
class KatanaDiscovery:
    """Discover URLs with Katana while preserving its breadth-first output priority."""

    def discover(
        self,
        seed: str,
        options: DiscoveryOptions,
        *,
        workers: int,
        max_url_length: int,
        max_response_bytes: int,
    ) -> tuple[str, ...]:
        result = _execute_katana(
            _katana_command(seed, options, workers=workers, max_response_bytes=max_response_bytes),
            options.timeout + 5,
        )
        if result.returncode != 0:
            raise WordlisterError(f"katana exited with status {result.returncode}")

        discovered: list[str] = []
        seen: set[str] = set()
        records_seen = 0
        for raw_line in result.stdout.splitlines():
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            raw_url = _katana_record_url(item)
            if raw_url is None:
                continue
            records_seen += 1
            try:
                url = normalize_discovered_url(raw_url, max_length=max_url_length)
            except InvalidTargetError:
                continue
            if (
                url not in seen
                and _url_in_scope(url, seed, options.mode)
                and not _is_asset_url(url)
            ):
                seen.add(url)
                discovered.append(url)

        if result.stdout.strip() and records_seen == 0:
            raise WordlisterError("katana returned an unsupported output format")
        return tuple(discovered)


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1].lower()


def _burp_item_fields(item: ET.Element) -> dict[str, ET.Element]:
    return {_xml_local_name(child.tag): child for child in item}


def _element_text(fields: dict[str, ET.Element], name: str) -> str:
    element = fields.get(name)
    return (element.text or "") if element is not None else ""


def _burp_request_target(request: ET.Element) -> str | None:
    encoded = request.text or ""
    if request.attrib.get("base64", "false").lower() == "true":
        compact = "".join(encoded.split())
        if len(compact) > (MAX_BURP_REQUEST_BYTES * 4 // 3) + 4:
            raise WordlisterError("Burp history request exceeded the supported size limit")
        try:
            request_bytes = base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error) as error:
            raise WordlisterError("Burp history contains an invalid Base64 request") from error
    else:
        request_bytes = encoded.encode("utf-8")
    if len(request_bytes) > MAX_BURP_REQUEST_BYTES:
        raise WordlisterError("Burp history request exceeded the supported size limit")

    first_line = request_bytes.splitlines()[0] if request_bytes.splitlines() else b""
    parts = first_line.decode("latin-1").split()
    return parts[1] if len(parts) >= 2 else None


def _reconstruct_burp_item_url(fields: dict[str, ET.Element]) -> str | None:
    request = fields.get("request")
    if request is None:
        return None
    target = _burp_request_target(request)
    if not target:
        return None
    if target.startswith(("http://", "https://")):
        return target
    if not target.startswith("/"):
        return None

    protocol = _element_text(fields, "protocol").lower()
    host = _element_text(fields, "host").strip()
    port_text = _element_text(fields, "port").strip()
    if protocol not in {"http", "https"} or not host:
        return None
    try:
        port = int(port_text) if port_text else (443 if protocol == "https" else 80)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    rendered_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    default_port = 443 if protocol == "https" else 80
    authority = rendered_host if port == default_port else f"{rendered_host}:{port}"
    return f"{protocol}://{authority}{target}"


def _iter_burp_xml_urls(path: Path) -> Iterable[str]:
    with path.open("rb") as source:
        prefix = source.read(64 * 1024).upper()
        if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
            raise WordlisterError("Burp history XML declarations are not supported")
    try:
        item_count = 0
        for _event, element in ET.iterparse(path, events=("end",)):
            if _xml_local_name(element.tag) != "item":
                continue
            item_count += 1
            if item_count > MAX_BURP_HISTORY_ITEMS:
                raise WordlisterError("Burp history item count exceeded the supported limit")
            fields = _burp_item_fields(element)
            url = _element_text(fields, "url").strip()
            if url:
                yield url
            else:
                reconstructed = _reconstruct_burp_item_url(fields)
                if reconstructed:
                    yield reconstructed
            element.clear()
    except ET.ParseError as error:
        raise WordlisterError("Burp history file contains malformed XML") from error


def _iter_burp_text_urls(path: Path) -> Iterable[str]:
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            for raw_line in source:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) >= 3 and "://" in fields[1]:
                    yield urljoin(fields[1].rstrip("/") + "/", fields[2].lstrip("/"))
                elif line.startswith(("http://", "https://")):
                    yield line
    except UnicodeError as error:
        raise WordlisterError("Burp history text export must use UTF-8") from error


def read_burp_history_urls(
    paths: Sequence[Path],
    *,
    max_url_length: int,
) -> tuple[str, ...]:
    """Read URL-only evidence from Burp XML, TSV, or plain-text history exports."""

    urls: list[str] = []
    seen: set[str] = set()
    for path in paths:
        try:
            size = path.stat().st_size
        except OSError as error:
            raise WordlisterError(f"could not read Burp history file: {error}") from error
        if size > MAX_BURP_HISTORY_BYTES:
            raise WordlisterError("Burp history file exceeded the supported size limit")
        try:
            with path.open("rb") as source:
                first = source.read(4096).lstrip()
        except OSError as error:
            raise WordlisterError(f"could not read Burp history file: {error}") from error
        candidates = (
            _iter_burp_xml_urls(path) if first.startswith(b"<") else _iter_burp_text_urls(path)
        )
        for raw_url in candidates:
            try:
                url = normalize_discovered_url(raw_url, max_length=max_url_length)
            except InvalidTargetError:
                continue
            if url not in seen and not _is_asset_url(url):
                seen.add(url)
                urls.append(url)
    return tuple(urls)


def discover_targets(
    targets: Sequence[str],
    *,
    options: DiscoveryOptions,
    workers: int,
    max_url_length: int,
    max_response_bytes: int,
    burp_history_paths: Sequence[Path] = (),
    provider: DiscoveryProvider | None = None,
) -> tuple[str, ...]:
    """Combine seeds, Burp history, and optional Katana results under one policy boundary."""

    if workers < 1:
        raise ValueError("workers must be at least 1")
    seeds = tuple(
        dict.fromkeys(
            normalize_discovered_url(target.strip(), max_length=max_url_length)
            for target in targets
            if target.strip()
        )
    )
    burp_urls = read_burp_history_urls(burp_history_paths, max_url_length=max_url_length)
    active_provider = provider or KatanaDiscovery()

    selected: list[str] = []
    for seed in seeds:
        candidates: list[str] = [seed]
        candidates.extend(url for url in burp_urls if _url_in_scope(url, seed, options.mode))
        if options.provider == "katana" and options.mode != "single" and options.max_depth > 0:
            candidates.extend(
                active_provider.discover(
                    seed,
                    options,
                    workers=workers,
                    max_url_length=max_url_length,
                    max_response_bytes=max_response_bytes,
                )
            )
        selected.extend(tuple(dict.fromkeys(candidates))[: options.max_pages])
    return tuple(dict.fromkeys(selected))
