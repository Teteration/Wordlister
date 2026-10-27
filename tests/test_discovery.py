import os
import unittest
from unittest.mock import Mock, patch

from wordlister_core.discovery import (
    _execute_hakrawler,
    _hakrawler_command,
    _ProcessResult,
    discover_targets,
    normalize_discovered_url,
)
from wordlister_core.errors import WordlisterError
from wordlister_core.models import DiscoveryOptions


class DiscoveryTests(unittest.TestCase):
    def test_normalizes_fragment_host_case_and_default_port(self) -> None:
        self.assertEqual(
            "https://example.com/path?view=full",
            normalize_discovered_url(
                "HTTPS://Example.COM:443/path?view=full#section",
                max_length=8192,
            ),
        )

    def test_none_provider_preserves_single_page_behavior_without_subprocess(self) -> None:
        with patch("wordlister_core.discovery._execute_hakrawler") as execute:
            targets = discover_targets(
                ["https://example.com/one", "https://example.com/one"],
                options=DiscoveryOptions(),
                workers=2,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(("https://example.com/one",), targets)
        execute.assert_not_called()

    def test_builds_bounded_hakrawler_command(self) -> None:
        command = _hakrawler_command(
            DiscoveryOptions(
                provider="hakrawler",
                mode="subdomain",
                max_depth=3,
                timeout=45,
                executable="/opt/tools/hakrawler",
            ),
            workers=7,
            max_response_bytes=2049,
        )

        self.assertEqual(
            [
                "/opt/tools/hakrawler",
                "-json",
                "-u",
                "-d",
                "3",
                "-t",
                "7",
                "-timeout",
                "45",
                "-size",
                "3",
                "-dr",
                "-subs",
            ],
            command,
        )

    def test_filters_output_by_scope_assets_and_page_limit(self) -> None:
        output = b"\n".join(
            (
                b'{"Source":"href","URL":"https://example.com/one#top"}',
                b'{"Source":"href","URL":"https://example.com/two"}',
                b'{"Source":"href","URL":"https://example.com/three"}',
                b'{"Source":"href","URL":"https://other.example.net/out"}',
                b'{"Source":"script","URL":"https://example.com/static/app.js"}',
            )
        )
        with patch(
            "wordlister_core.discovery._execute_hakrawler",
            return_value=_ProcessResult(returncode=0, stdout=output, stderr=b""),
        ):
            targets = discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(
                    provider="hakrawler",
                    mode="domain",
                    max_depth=2,
                    max_pages=3,
                ),
                workers=2,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(
            (
                "https://example.com/",
                "https://example.com/one",
                "https://example.com/three",
            ),
            targets,
        )

    def test_subdomain_mode_accepts_child_hosts(self) -> None:
        output = b'{"Source":"href","URL":"https://api.example.com/users"}\n'
        with patch(
            "wordlister_core.discovery._execute_hakrawler",
            return_value=_ProcessResult(returncode=0, stdout=output, stderr=b""),
        ):
            targets = discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(
                    provider="hakrawler",
                    mode="subdomain",
                    max_depth=1,
                ),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(
            ("https://example.com/", "https://api.example.com/users"),
            targets,
        )

    def test_subdomain_mode_does_not_treat_ip_suffixes_as_child_hosts(self) -> None:
        output = b'{"URL":"https://api.192.0.2.10/users"}\n'
        with patch(
            "wordlister_core.discovery._execute_hakrawler",
            return_value=_ProcessResult(returncode=0, stdout=output, stderr=b""),
        ):
            targets = discover_targets(
                ["https://192.0.2.10/"],
                options=DiscoveryOptions(
                    provider="hakrawler",
                    mode="subdomain",
                    max_depth=1,
                ),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(("https://192.0.2.10/",), targets)

    def test_rejects_unsupported_nonempty_output(self) -> None:
        with (
            patch(
                "wordlister_core.discovery._execute_hakrawler",
                return_value=_ProcessResult(returncode=0, stdout=b"not-json\n", stderr=b""),
            ),
            self.assertRaisesRegex(WordlisterError, "unsupported output format"),
        ):
            discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(provider="hakrawler", max_depth=1),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

    def test_rejects_json_with_an_unsupported_schema(self) -> None:
        with (
            patch(
                "wordlister_core.discovery._execute_hakrawler",
                return_value=_ProcessResult(
                    returncode=0,
                    stdout=b'{"url":"https://example.com/one"}\n',
                    stderr=b"",
                ),
            ),
            self.assertRaisesRegex(WordlisterError, "unsupported output format"),
        ):
            discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(provider="hakrawler", max_depth=1),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

    def test_reports_missing_hakrawler_binary(self) -> None:
        with (
            patch("wordlister_core.discovery.subprocess.Popen", side_effect=FileNotFoundError),
            self.assertRaisesRegex(WordlisterError, "executable was not found"),
        ):
            _execute_hakrawler(["hakrawler"], "https://example.com/", 1)

    def test_reports_nonzero_hakrawler_exit_without_exposing_stderr(self) -> None:
        with (
            patch(
                "wordlister_core.discovery._execute_hakrawler",
                return_value=_ProcessResult(
                    returncode=2,
                    stdout=b"",
                    stderr=b"untrusted diagnostic\n",
                ),
            ),
            self.assertRaisesRegex(WordlisterError, "exited with status 2") as raised,
        ):
            discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(provider="hakrawler", max_depth=1),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertNotIn("untrusted diagnostic", str(raised.exception))

    def test_executes_without_shell_and_removes_proxy_environment(self) -> None:
        captured: dict[str, object] = {}

        class FakeProcess:
            returncode = 0

            def poll(self) -> int:
                return 0

            def kill(self) -> None:
                raise AssertionError("kill should not be called")

            def wait(self) -> int:
                raise AssertionError("wait should not be called")

        def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
            captured["command"] = command
            captured["input"] = kwargs["stdin"].read()
            captured.update(kwargs)
            return FakeProcess()

        with (
            patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.invalid", "SAFE_VALUE": "kept"}),
            patch("wordlister_core.discovery.subprocess.Popen", side_effect=fake_popen),
        ):
            result = _execute_hakrawler(["hakrawler", "-json"], "https://example.com/", 10)

        self.assertEqual(0, result.returncode)
        self.assertNotIn("HTTPS_PROXY", captured["env"])
        self.assertEqual("kept", captured["env"]["SAFE_VALUE"])
        self.assertNotIn("shell", captured)
        self.assertEqual(b"https://example.com/\n", captured["input"])

    def test_kills_hakrawler_after_timeout(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.returncode = None

        with (
            patch("wordlister_core.discovery.subprocess.Popen", return_value=process),
            patch("wordlister_core.discovery.time.monotonic", side_effect=(0.0, 7.0)),
            self.assertRaisesRegex(WordlisterError, "exceeded.*timeout"),
        ):
            _execute_hakrawler(["hakrawler"], "https://example.com/", 1)

        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_kills_hakrawler_when_output_exceeds_limit(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.returncode = None

        def fake_popen(command: list[str], **kwargs: object) -> Mock:
            del command
            kwargs["stdout"].write(b"x")
            kwargs["stdout"].flush()
            return process

        with (
            patch("wordlister_core.discovery.subprocess.Popen", side_effect=fake_popen),
            patch("wordlister_core.discovery.MAX_CRAWLER_OUTPUT_BYTES", 0),
            patch("wordlister_core.discovery.time.monotonic", return_value=0.0),
            self.assertRaisesRegex(WordlisterError, "output exceeded"),
        ):
            _execute_hakrawler(["hakrawler"], "https://example.com/", 10)

        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_validates_provider_mode_and_executable(self) -> None:
        invalid_options = (
            {"provider": "gospider"},
            {"mode": "origin"},
            {"executable": ""},
            {"executable": "hakrawler\x00bad"},
        )

        for values in invalid_options:
            with self.subTest(values=values), self.assertRaises(ValueError):
                DiscoveryOptions(**values)


if __name__ == "__main__":
    unittest.main()
