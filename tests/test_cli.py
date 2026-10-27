import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wordlister_core.cli import EXIT_ERROR, EXIT_PARTIAL, EXIT_SUCCESS, main
from wordlister_core.models import DiscoveryOptions, TargetFailure, WordInfo, WordlistResult


class CliTests(unittest.TestCase):
    def test_list_output_remains_backward_compatible(self) -> None:
        result = WordlistResult(words=("account", "profile"), failures=(), processed_targets=1)
        stdout = io.StringIO()

        with (
            patch("wordlister_core.cli.build_wordlist", return_value=result),
            patch("sys.stdout", stdout),
            patch("sys.stderr", io.StringIO()),
        ):
            exit_code = main(["--url", "https://example.com"])

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual("['account', 'profile']\n", stdout.getvalue())

    def test_lines_output_keeps_stdout_machine_readable(self) -> None:
        result = WordlistResult(words=("account", "profile"), failures=(), processed_targets=1)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("wordlister_core.cli.build_wordlist", return_value=result),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            exit_code = main(["--url", "https://example.com", "--output-format", "lines"])

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual("account\nprofile\n", stdout.getvalue())
        self.assertIn("extracted 2 words", stderr.getvalue())

    def test_partial_result_returns_distinct_exit_code_and_sanitized_warning(self) -> None:
        result = WordlistResult(
            words=("account",),
            failures=(
                TargetFailure(
                    target="https://example.com/login?token",
                    code="timeout",
                    message="request timed out",
                ),
            ),
            processed_targets=1,
        )
        stderr = io.StringIO()

        with (
            patch("wordlister_core.cli.build_wordlist", return_value=result),
            patch("sys.stdout", io.StringIO()),
            patch("sys.stderr", stderr),
        ):
            exit_code = main(["--url", "https://example.com/login?token=secret"])

        self.assertEqual(EXIT_PARTIAL, exit_code)
        self.assertIn("https://example.com/login?token", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())

    def test_json_output_contains_score_sources_and_count(self) -> None:
        result = WordlistResult(
            words=("account",),
            failures=(),
            processed_targets=2,
            entries=(
                WordInfo(
                    word="account",
                    count=3,
                    score=7,
                    sources=("form.action", "url.path"),
                ),
            ),
        )
        stdout = io.StringIO()

        with (
            patch("wordlister_core.cli.build_wordlist", return_value=result),
            patch("sys.stdout", stdout),
            patch("sys.stderr", io.StringIO()),
        ):
            exit_code = main(["--url", "https://example.com", "--output-format", "json"])

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual(
            {
                "account": {
                    "score": 7,
                    "sources": ["form.action", "url.path"],
                    "count": 3,
                }
            },
            json.loads(stdout.getvalue()),
        )

    def test_input_file_ignores_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.txt"
            path.write_text(
                "# authorized targets\n\nhttps://example.com/one\nhttps://example.com/two\n",
                encoding="utf-8",
            )
            captured_targets: list[str] = []

            def fake_build(targets: list[str], **_: object) -> WordlistResult:
                captured_targets.extend(targets)
                return WordlistResult(words=(), failures=(), processed_targets=2)

            with (
                patch("wordlister_core.cli.build_wordlist", side_effect=fake_build),
                patch("sys.stdout", io.StringIO()),
                patch("sys.stderr", io.StringIO()),
            ):
                exit_code = main(["--input-file", str(path)])

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual(
            ["https://example.com/one", "https://example.com/two"],
            captured_targets,
        )

    def test_external_discovery_targets_are_passed_to_pipeline(self) -> None:
        captured_targets: list[str] = []
        captured_options: list[DiscoveryOptions] = []

        def fake_discover(targets: list[str], **kwargs: object) -> tuple[str, ...]:
            captured_options.append(kwargs["options"])
            self.assertEqual(["https://example.com"], targets)
            return ("https://example.com/", "https://example.com/account")

        def fake_build(targets: list[str], **_: object) -> WordlistResult:
            captured_targets.extend(targets)
            return WordlistResult(words=(), failures=(), processed_targets=2)

        with (
            patch("wordlister_core.cli.discover_targets", side_effect=fake_discover),
            patch("wordlister_core.cli.build_wordlist", side_effect=fake_build),
            patch("sys.stdout", io.StringIO()),
            patch("sys.stderr", io.StringIO()),
        ):
            exit_code = main(
                [
                    "--url",
                    "https://example.com",
                    "--crawler",
                    "hakrawler",
                    "--mode",
                    "subdomain",
                    "--depth",
                    "3",
                    "--max-pages",
                    "250",
                    "--crawler-timeout",
                    "45",
                    "--crawler-path",
                    "/opt/tools/hakrawler",
                ]
            )

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertEqual(
            DiscoveryOptions(
                provider="hakrawler",
                mode="subdomain",
                max_depth=3,
                max_pages=250,
                timeout=45,
                executable="/opt/tools/hakrawler",
            ),
            captured_options[0],
        )
        self.assertEqual(
            ["https://example.com/", "https://example.com/account"],
            captured_targets,
        )

    def test_depth_without_crawler_returns_clear_error(self) -> None:
        stderr = io.StringIO()

        with (
            patch("sys.stdout", io.StringIO()),
            patch("sys.stderr", stderr),
        ):
            exit_code = main(["--url", "https://example.com", "--depth", "2"])

        self.assertEqual(EXIT_ERROR, exit_code)
        self.assertIn("--depth requires --crawler hakrawler", stderr.getvalue())

    def test_invalid_options_return_error_without_traceback(self) -> None:
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            exit_code = main(
                [
                    "--url",
                    "https://example.com",
                    "--min-length",
                    "10",
                    "--max-length",
                    "3",
                ]
            )

        self.assertEqual(EXIT_ERROR, exit_code)
        self.assertIn("max_length", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
