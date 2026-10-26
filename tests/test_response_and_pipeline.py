import unittest

from wordlister_core.errors import FetchError
from wordlister_core.models import ExtractOptions, FetchedResponse, RedirectHop
from wordlister_core.pipeline import build_wordlist
from wordlister_core.response import extract_response


class ResponseExtractorTests(unittest.TestCase):
    def test_uses_content_type_headers_and_redirect_history(self) -> None:
        response = FetchedResponse(
            requested_url="https://example.com/start",
            final_url="https://example.com/api/profile",
            status_code=200,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Request-ID": "opaque-request-id-that-should-not-be-used",
            },
            history=(
                RedirectHop(
                    url="https://example.com/start",
                    status_code=302,
                    headers={"Location": "/api/profile"},
                ),
            ),
            text='{"displayName": "securityResearcher", "password": "DoNotLeakMe123"}',
        )

        words = extract_response(response, include_comments=False)

        self.assertTrue(
            {
                "start",
                "api",
                "profile",
                "Location",
                "displayName",
                "securityResearcher",
                "password",
                "X-Request-ID",
            }.issubset(words)
        )
        self.assertNotIn("DoNotLeakMe123", words)
        self.assertNotIn("opaque-request-id-that-should-not-be-used", words)


class FakeFetcher:
    def fetch(self, url: str) -> FetchedResponse:
        if "broken" in url:
            raise FetchError(url, "network_error", "request failed")
        return FetchedResponse(
            requested_url=url,
            final_url=url,
            status_code=200,
            headers={"Content-Type": "application/json"},
            history=(),
            text='{"accountSettings": "profileDashboard"}',
        )


class PipelineTests(unittest.TestCase):
    def test_returns_deterministic_words_and_visible_failures(self) -> None:
        result = build_wordlist(
            [
                "https://example.com/api/users",
                "https://example.com/api/users",
                "https://broken.example.com/fail",
            ],
            fetcher=FakeFetcher(),
            extract_options=ExtractOptions(min_length=3),
            workers=2,
        )

        self.assertEqual(tuple(sorted(result.words)), result.words)
        self.assertEqual(1, len(result.failures))
        self.assertEqual("network_error", result.failures[0].code)
        self.assertIn("accountSettings", result.words)
        self.assertIn("profileDashboard", result.words)
        self.assertEqual(2, result.processed_targets)


if __name__ == "__main__":
    unittest.main()
