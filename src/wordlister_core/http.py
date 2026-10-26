"""Bounded HTTP transport for user-supplied targets."""

from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from wordlister_core.errors import FetchError, InvalidTargetError
from wordlister_core.models import FetchedResponse, HttpOptions, RedirectHop

REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def sanitize_url(url: str) -> str:
    """Remove credentials, query values, and fragments from diagnostic output."""

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        port = parsed.port
        if port:
            hostname = f"{hostname}:{port}"
        query_names = "&".join(
            part.split("=", maxsplit=1)[0] for part in parsed.query.split("&") if part
        )
        return urlunparse((parsed.scheme, hostname, parsed.path, "", query_names, ""))
    except (TypeError, ValueError):
        return "<invalid-url>"


def validate_http_url(url: str, *, max_length: int = 8 * 1024) -> str:
    """Validate a top-level or redirect URL against Wordlister's HTTP contract."""

    if not url or len(url) > max_length:
        raise InvalidTargetError("target URL is empty or exceeds the configured limit")
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as error:
        raise InvalidTargetError("target URL contains an invalid host or port") from error
    if scheme not in {"http", "https"}:
        raise InvalidTargetError("target URL must use http or https")
    if not hostname:
        raise InvalidTargetError("target URL must include a hostname")
    if username is not None or password is not None:
        raise InvalidTargetError("credentials in target URLs are not supported")
    del port
    return url


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port or default_port


def _redirect_allowed(current_url: str, next_url: str) -> bool:
    current_scheme, current_host, current_port = _origin(current_url)
    next_scheme, next_host, next_port = _origin(next_url)
    if (current_scheme, current_host, current_port) == (
        next_scheme,
        next_host,
        next_port,
    ):
        return True
    return (
        current_scheme == "http"
        and next_scheme == "https"
        and current_host == next_host
        and current_port == 80
        and next_port == 443
    )


class HttpClient:
    """Fetch URLs with explicit redirects, safe defaults, and body-size limits."""

    def __init__(
        self,
        options: HttpOptions | None = None,
        *,
        session_factory: Callable[[], Any] = requests.Session,
    ) -> None:
        self.options = options or HttpOptions()
        self._session_factory = session_factory

    def fetch(self, url: str) -> FetchedResponse:
        validate_http_url(url, max_length=self.options.max_url_length)
        session = self._session_factory()
        session.trust_env = False
        session.headers["User-Agent"] = self.options.user_agent
        requested_url = url
        current_url = url
        history: list[RedirectHop] = []

        try:
            for redirect_count in range(self.options.max_redirects + 1):
                response = None
                try:
                    response = session.get(
                        current_url,
                        allow_redirects=False,
                        stream=True,
                        timeout=(self.options.connect_timeout, self.options.read_timeout),
                    )
                    headers = dict(response.headers)

                    if response.status_code in REDIRECT_STATUS_CODES:
                        location = headers.get("Location") or headers.get("location")
                        if not location:
                            raise FetchError(
                                sanitize_url(current_url),
                                "invalid_redirect",
                                "redirect response did not include a Location header",
                            )
                        if redirect_count >= self.options.max_redirects:
                            raise FetchError(
                                sanitize_url(current_url),
                                "too_many_redirects",
                                "redirect limit exceeded",
                            )
                        next_url = urljoin(current_url, location)
                        try:
                            validate_http_url(
                                next_url,
                                max_length=self.options.max_url_length,
                            )
                        except InvalidTargetError as error:
                            raise FetchError(
                                sanitize_url(current_url),
                                "redirect_blocked",
                                str(error),
                            ) from error
                        if not _redirect_allowed(current_url, next_url):
                            raise FetchError(
                                sanitize_url(current_url),
                                "redirect_blocked",
                                "cross-origin or HTTPS-downgrade redirect was blocked",
                            )
                        history.append(
                            RedirectHop(
                                url=current_url,
                                status_code=response.status_code,
                                headers=headers,
                            )
                        )
                        current_url = next_url
                        continue

                    body = self._read_body(response, current_url)
                    encoding = response.encoding or "utf-8"
                    text = body.decode(encoding, errors="replace")
                    return FetchedResponse(
                        requested_url=requested_url,
                        final_url=response.url or current_url,
                        status_code=response.status_code,
                        headers=headers,
                        history=tuple(history),
                        text=text,
                    )
                finally:
                    if response is not None:
                        response.close()
        except FetchError:
            raise
        except requests.Timeout as error:
            raise FetchError(sanitize_url(current_url), "timeout", "request timed out") from error
        except requests.RequestException as error:
            raise FetchError(
                sanitize_url(current_url), "network_error", "request failed"
            ) from error
        finally:
            session.close()

        raise FetchError(sanitize_url(current_url), "too_many_redirects", "redirect limit exceeded")

    def _read_body(self, response: Any, url: str) -> bytes:
        content_length = response.headers.get("Content-Length") or response.headers.get(
            "content-length"
        )
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self.options.max_response_bytes:
                raise FetchError(
                    sanitize_url(url),
                    "response_too_large",
                    "response exceeds the configured size limit",
                )

        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > self.options.max_response_bytes:
                raise FetchError(
                    sanitize_url(url),
                    "response_too_large",
                    "response exceeds the configured size limit",
                )
        return bytes(body)
