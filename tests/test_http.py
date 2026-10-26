import unittest

from wordlister_core.errors import FetchError, InvalidTargetError
from wordlister_core.http import HttpClient, sanitize_url, validate_http_url
from wordlister_core.models import HttpOptions


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (b"ok",),
        encoding: str | None = "utf-8",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int) -> tuple[bytes, ...]:
        del chunk_size
        return self._chunks

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.headers: dict[str, str] = {}
        self.trust_env = True
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class UrlValidationTests(unittest.TestCase):
    def test_rejects_non_http_schemes_and_url_credentials(self) -> None:
        for url in ("httpx://example.com", "file:///etc/passwd", "javascript:alert(1)"):
            with self.subTest(url=url), self.assertRaises(InvalidTargetError):
                validate_http_url(url)

        with self.assertRaises(InvalidTargetError):
            validate_http_url("https://user:password@example.com/private")

    def test_malformed_hosts_and_ports_are_rejected_and_safely_rendered(self) -> None:
        malformed_urls = ("https://[broken", "https://example.com:not-a-port/path?token=secret")

        for url in malformed_urls:
            with self.subTest(url=url):
                with self.assertRaises(InvalidTargetError):
                    validate_http_url(url)
                rendered = sanitize_url(url)
                self.assertNotIn("secret", rendered)


class HttpClientTests(unittest.TestCase):
    def test_enforces_declared_response_size_limit(self) -> None:
        response = FakeResponse(
            url="https://example.com/data",
            headers={"Content-Length": "20"},
        )
        session = FakeSession([response])
        client = HttpClient(HttpOptions(max_response_bytes=10), session_factory=lambda: session)

        with self.assertRaises(FetchError) as context:
            client.fetch("https://example.com/data")

        self.assertEqual("response_too_large", context.exception.code)
        self.assertTrue(response.closed)
        self.assertTrue(session.closed)

    def test_enforces_streamed_response_size_limit(self) -> None:
        response = FakeResponse(
            url="https://example.com/data",
            chunks=(b"123456", b"789012"),
        )
        client = HttpClient(
            HttpOptions(max_response_bytes=10),
            session_factory=lambda: FakeSession([response]),
        )

        with self.assertRaises(FetchError) as context:
            client.fetch("https://example.com/data")

        self.assertEqual("response_too_large", context.exception.code)

    def test_blocks_cross_origin_redirects_by_default(self) -> None:
        redirect = FakeResponse(
            url="https://example.com/start",
            status_code=302,
            headers={"Location": "https://other.example.net/login"},
            chunks=(),
        )
        client = HttpClient(HttpOptions(), session_factory=lambda: FakeSession([redirect]))

        with self.assertRaises(FetchError) as context:
            client.fetch("https://example.com/start")

        self.assertEqual("redirect_blocked", context.exception.code)

    def test_fetches_with_bounded_safe_request_settings(self) -> None:
        response = FakeResponse(
            url="https://example.com/data",
            headers={"Content-Type": "text/plain"},
            chunks=(b"accountSettings",),
        )
        session = FakeSession([response])
        options = HttpOptions(connect_timeout=2.0, read_timeout=4.0)
        client = HttpClient(options, session_factory=lambda: session)

        result = client.fetch("https://example.com/data")

        self.assertEqual("accountSettings", result.text)
        self.assertFalse(session.trust_env)
        self.assertEqual(
            {
                "allow_redirects": False,
                "stream": True,
                "timeout": (2.0, 4.0),
            },
            session.calls[0][1],
        )


if __name__ == "__main__":
    unittest.main()
