import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from wordlister_core.discovery import (
    _execute_katana,
    _katana_command,
    _ProcessResult,
    discover_targets,
    normalize_discovered_url,
    read_burp_history_urls,
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

    def test_none_provider_preserves_seed_without_subprocess(self) -> None:
        with patch("wordlister_core.discovery._execute_katana") as execute:
            targets = discover_targets(
                ["https://example.com/one", "https://example.com/one"],
                options=DiscoveryOptions(),
                workers=2,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(("https://example.com/one",), targets)
        execute.assert_not_called()

    def test_builds_bounded_katana_command_for_installed_cli(self) -> None:
        command = _katana_command(
            "https://example.com/",
            DiscoveryOptions(
                provider="katana",
                mode="subdomain",
                max_depth=3,
                timeout=45,
                executable="/opt/tools/katana",
            ),
            workers=7,
            max_response_bytes=2049,
        )

        self.assertEqual(
            [
                "/opt/tools/katana",
                "-u",
                "https://example.com/",
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
                "3",
                "-concurrency",
                "7",
                "-parallelism",
                "1",
                "-timeout",
                "45",
                "-crawl-duration",
                "45s",
                "-max-response-size",
                "2049",
                "-crawl-scope",
                r"^https://(?:[^/?#.]+\.)*example\.com(?::443)?(?:[/?#]|$)",
                "-js-crawl",
            ],
            command,
        )

    def test_preserves_katana_order_while_filtering_scope_assets_and_limit(self) -> None:
        output = b"\n".join(
            (
                b'{"request":{"endpoint":"https://example.com/shallow#top"}}',
                b'{"request":{"endpoint":"https://example.com/second"}}',
                b'{"request":{"endpoint":"https://example.com/deep/details/1"}}',
                b'{"request":{"endpoint":"https://other.example.net/out"}}',
                b'{"request":{"endpoint":"https://example.com/static/app.js"}}',
            )
        )
        with patch(
            "wordlister_core.discovery._execute_katana",
            return_value=_ProcessResult(returncode=0, stdout=output, stderr=b""),
        ):
            targets = discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(
                    provider="katana",
                    mode="domain",
                    max_depth=5,
                    max_pages=3,
                ),
                workers=2,
                max_url_length=8192,
                max_response_bytes=1024,
            )

        self.assertEqual(
            (
                "https://example.com/",
                "https://example.com/shallow",
                "https://example.com/second",
            ),
            targets,
        )

    def test_reads_burp_xml_tsv_and_url_list_exports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "history.xml"
            tsv_path = root / "history.tsv"
            list_path = root / "urls.txt"
            xml_path.write_text(
                "<?xml version='1.0'?><items><item><url>https://example.com/xml?a=1</url>"
                "</item><item><url>https://example.com/static/app.js</url></item></items>",
                encoding="utf-8",
            )
            tsv_path.write_text(
                "GET\thttps://example.com:443\t/account/profile?tab=security\tfalse\t200\n",
                encoding="utf-8",
            )
            list_path.write_text(
                "# exported URLs\nhttps://example.com/plain#fragment\n",
                encoding="utf-8",
            )

            urls = read_burp_history_urls(
                [xml_path, tsv_path, list_path],
                max_url_length=8192,
            )

        self.assertEqual(
            (
                "https://example.com/xml?a=1",
                "https://example.com/account/profile?tab=security",
                "https://example.com/plain",
            ),
            urls,
        )

    def test_reconstructs_burp_xml_urls_from_base64_and_raw_requests(self) -> None:
        encoded_request = base64.b64encode(
            b"POST /base64/path?token=redacted HTTP/1.1\r\n\r\n"
        ).decode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.xml"
            path.write_text(
                "<items>"
                "<item><host>example.com</host><port>8443</port><protocol>https</protocol>"
                f"<request base64='true'>{encoded_request}</request></item>"
                "<item><host>example.com</host><port>80</port><protocol>http</protocol>"
                "<request base64='false'>GET /raw/path HTTP/1.1\n\n</request></item>"
                "</items>",
                encoding="utf-8",
            )

            urls = read_burp_history_urls([path], max_url_length=8192)

        self.assertEqual(
            (
                "https://example.com:8443/base64/path?token=redacted",
                "http://example.com/raw/path",
            ),
            urls,
        )

    def test_rejects_invalid_base64_burp_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.xml"
            path.write_text(
                "<items><item><host>example.com</host><port>443</port>"
                "<protocol>https</protocol><request base64='true'>%%%bad%%%</request>"
                "</item></items>",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(WordlisterError, "invalid Base64 request"):
                read_burp_history_urls([path], max_url_length=8192)

    def test_prioritizes_seed_then_burp_then_katana_with_shared_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "history.tsv"
            history.write_text(
                "GET\thttps://example.com\t/from-burp-one\tfalse\t200\n"
                "GET\thttps://example.com\t/from-burp-two\tfalse\t200\n",
                encoding="utf-8",
            )
            output = b'{"request":{"endpoint":"https://example.com/from-katana"}}\n'
            with patch(
                "wordlister_core.discovery._execute_katana",
                return_value=_ProcessResult(returncode=0, stdout=output, stderr=b""),
            ):
                targets = discover_targets(
                    ["https://example.com/"],
                    options=DiscoveryOptions(
                        provider="katana",
                        max_depth=2,
                        max_pages=3,
                    ),
                    workers=1,
                    max_url_length=8192,
                    max_response_bytes=1024,
                    burp_history_paths=[history],
                )

        self.assertEqual(
            (
                "https://example.com/",
                "https://example.com/from-burp-one",
                "https://example.com/from-burp-two",
            ),
            targets,
        )

    def test_rejects_burp_xml_with_doctype(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.xml"
            path.write_text(
                "<!DOCTYPE items [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
                "<items><item><url>&xxe;</url></item></items>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WordlisterError, "declarations are not supported"):
                read_burp_history_urls([path], max_url_length=8192)

    def test_rejects_unsupported_nonempty_katana_output(self) -> None:
        with (
            patch(
                "wordlister_core.discovery._execute_katana",
                return_value=_ProcessResult(returncode=0, stdout=b"not-json\n", stderr=b""),
            ),
            self.assertRaisesRegex(WordlisterError, "unsupported output format"),
        ):
            discover_targets(
                ["https://example.com/"],
                options=DiscoveryOptions(provider="katana", max_depth=1),
                workers=1,
                max_url_length=8192,
                max_response_bytes=1024,
            )

    def test_reports_missing_katana_binary(self) -> None:
        with (
            patch("wordlister_core.discovery.subprocess.Popen", side_effect=FileNotFoundError),
            self.assertRaisesRegex(WordlisterError, "executable was not found"),
        ):
            _execute_katana(["katana"], 1)

    def test_reports_nonzero_katana_exit_without_exposing_stderr(self) -> None:
        with (
            patch(
                "wordlister_core.discovery._execute_katana",
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
                options=DiscoveryOptions(provider="katana", max_depth=1),
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
            captured.update(kwargs)
            return FakeProcess()

        with (
            patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.invalid", "SAFE_VALUE": "kept"}),
            patch("wordlister_core.discovery.subprocess.Popen", side_effect=fake_popen),
        ):
            result = _execute_katana(["katana", "-jsonl"], 10)

        self.assertEqual(0, result.returncode)
        self.assertNotIn("HTTPS_PROXY", captured["env"])
        self.assertEqual("kept", captured["env"]["SAFE_VALUE"])
        self.assertNotIn("shell", captured)

    def test_kills_katana_after_timeout(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.returncode = None

        with (
            patch("wordlister_core.discovery.subprocess.Popen", return_value=process),
            patch("wordlister_core.discovery.time.monotonic", side_effect=(0.0, 2.0)),
            self.assertRaisesRegex(WordlisterError, "exceeded.*timeout"),
        ):
            _execute_katana(["katana"], 1)

        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_kills_katana_when_output_exceeds_limit(self) -> None:
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
            patch("wordlister_core.discovery.MAX_DISCOVERY_OUTPUT_BYTES", 0),
            patch("wordlister_core.discovery.time.monotonic", return_value=0.0),
            self.assertRaisesRegex(WordlisterError, "output exceeded"),
        ):
            _execute_katana(["katana"], 10)

        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()

    def test_validates_provider_mode_and_executable(self) -> None:
        invalid_options = (
            {"provider": "gospider"},
            {"mode": "origin"},
            {"executable": ""},
            {"executable": "katana\x00bad"},
        )

        for values in invalid_options:
            with self.subTest(values=values), self.assertRaises(ValueError):
                DiscoveryOptions(**values)


if __name__ == "__main__":
    unittest.main()
