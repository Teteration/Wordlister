"""Command-line interface for Wordlister."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from wordlister_core.discovery import discover_targets
from wordlister_core.errors import WordlisterError
from wordlister_core.http import HttpClient
from wordlister_core.models import DiscoveryOptions, ExtractOptions, HttpOptions, WordlistResult
from wordlister_core.pipeline import build_wordlist

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_PARTIAL = 2


def build_parser() -> argparse.ArgumentParser:
    """Create the public CLI contract in one testable function."""

    parser = argparse.ArgumentParser(
        prog="wordlister",
        description="Build a target-specific wordlist from HTTP responses.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="single HTTP/HTTPS target to analyze")
    source.add_argument(
        "--input-file",
        type=Path,
        help="text file containing one HTTP/HTTPS URL per line",
    )
    parser.add_argument("--threads", type=int, default=5, help="concurrent targets (default: 5)")
    parser.add_argument("--min-length", type=int, default=1, help="minimum word length")
    parser.add_argument("--max-length", type=int, default=100, help="maximum word length")
    parser.add_argument(
        "--filter",
        dest="character_filter",
        choices=("ascii", "unicode"),
        default="unicode",
        help="character filter (default: unicode)",
    )
    parser.add_argument(
        "--drop-obfuscated",
        action="store_true",
        help="drop hex-like and opaque token values",
    )
    parser.add_argument(
        "--include-comments",
        action="store_true",
        help="extract candidates from HTML comments",
    )
    parser.add_argument(
        "--output-format",
        choices=("list", "lines", "json"),
        default="list",
        help="stdout format (default: list)",
    )
    parser.add_argument("--connect-timeout", type=float, default=3.05)
    parser.add_argument("--read-timeout", type=float, default=10.0)
    parser.add_argument("--max-response-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-redirects", type=int, default=5)

    parser.add_argument(
        "--crawler",
        choices=("none", "hakrawler"),
        default="none",
        help="optional external URL discovery provider (default: none)",
    )
    parser.add_argument(
        "--mode",
        choices=("single", "domain", "subdomain"),
        default="domain",
        help="crawler scope: seed only, exact host, or host plus child subdomains",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=0,
        help="maximum discovered-link depth (default: 0)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1000,
        help="maximum fetched pages per supplied seed, including the seed (default: 1000)",
    )
    parser.add_argument(
        "--crawler-timeout",
        type=int,
        default=120,
        help="maximum hakrawler runtime per supplied seed in seconds (default: 120)",
    )
    parser.add_argument(
        "--crawler-path",
        default="hakrawler",
        help="hakrawler executable name or path (default: hakrawler)",
    )
    return parser


def _read_targets(args: argparse.Namespace) -> list[str]:
    if args.url:
        return [args.url]
    try:
        return [
            line.strip()
            for line in args.input_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError as error:
        raise WordlisterError(f"could not read input file: {error}") from error


def _render_result(result: WordlistResult, output_format: str) -> None:
    if output_format == "list":
        print(list(result.words))
    elif output_format == "json":
        payload = {
            entry.word: {
                "score": entry.score,
                "sources": list(entry.sources),
                "count": entry.count,
            }
            for entry in result.entries
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for word in result.words:
            print(word)

    for failure in result.failures:
        print(
            f"warning: {failure.target}: {failure.code}: {failure.message}",
            file=sys.stderr,
        )
    print(
        f"extracted {len(result.words)} words from "
        f"{result.processed_targets} unique target(s); "
        f"{len(result.failures)} failure(s)",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, run the pipeline, and return a documented exit code."""

    args = build_parser().parse_args(argv)
    try:
        extract_options = ExtractOptions(
            min_length=args.min_length,
            max_length=args.max_length,
            character_filter=args.character_filter,
            drop_obfuscated=args.drop_obfuscated,
            include_comments=args.include_comments,
        )
        http_options = HttpOptions(
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            max_response_bytes=args.max_response_bytes,
            max_redirects=args.max_redirects,
        )
        discovery_options = DiscoveryOptions(
            provider=args.crawler,
            mode=args.mode,
            max_depth=args.depth,
            max_pages=args.max_pages,
            timeout=args.crawler_timeout,
            executable=args.crawler_path,
        )
        targets = _read_targets(args)
        if not targets:
            raise WordlisterError("no targets were found in the selected input")
        targets = list(
            discover_targets(
                targets,
                options=discovery_options,
                workers=args.threads,
                max_url_length=http_options.max_url_length,
                max_response_bytes=http_options.max_response_bytes,
            )
        )
        result = build_wordlist(
            targets,
            fetcher=HttpClient(http_options),
            extract_options=extract_options,
            workers=args.threads,
        )
    except (ValueError, WordlisterError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    _render_result(result, args.output_format)
    return EXIT_PARTIAL if result.failures else EXIT_SUCCESS
