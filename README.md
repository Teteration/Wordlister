# Wordlister

[![CI](https://github.com/Teteration/Wordlister/actions/workflows/ci.yml/badge.svg)](https://github.com/Teteration/Wordlister/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Wordlister builds **target-specific wordlists** from URLs and bounded HTTP responses. It is designed for authorized reconnaissance and fuzzing workflows where generic dictionaries miss application-specific routes, parameters, field names, and identifiers.

It does not ship with a dictionary and does not download third-party wordlists. Every output candidate comes from the targets you provide.

> Use Wordlister only against systems you own or are explicitly authorized to test.

## Highlights

- Extracts identifiers from URL hosts, paths, query strings, fragments, and nested URL values.
- Splits `camelCase`, `PascalCase`, `snake_case`, `kebab-case`, dotted names, and mixed identifiers while retaining useful originals.
- Parses HTML text, attributes, forms, linked resources, inline JavaScript, embedded JSON, and optional comments.
- Parses JSON keys and safe string values recursively with depth and node limits.
- Extracts selected response-header metadata and redirect paths without emitting cookie or authorization values.
- Uses deterministic output, bounded downloads, explicit timeouts, same-origin redirects, and visible per-target failures.
- Preserves the original `python3 wordlister.py` invocation while providing an installable `wordlister` command.

## Installation

```bash
git clone https://github.com/Teteration/Wordlister.git
cd Wordlister
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development tools:

```bash
python -m pip install -e '.[dev]'
```

The compatibility installation command is also supported:

```bash
python -m pip install -r requirements.txt
```

## Quick start

```bash
wordlister --url https://example.com --output-format lines
```

Or run directly from the repository:

```bash
python3 wordlister.py --url https://example.com --output-format lines
```

Analyze a prepared URL list:

```bash
wordlister \
  --input-file urls.txt \
  --threads 8 \
  --min-length 4 \
  --max-length 32 \
  --filter ascii \
  --drop-obfuscated \
  --output-format lines
```

Input files contain one HTTP/HTTPS URL per line. Blank lines and lines beginning with `#` are ignored.

## Where the words come from

| Source | Examples |
| --- | --- |
| Requested, redirected, and final URLs | host labels, path segments, filenames, query names, safe query values, fragments |
| HTML text | headings, labels, buttons, validation messages |
| HTML attributes | `id`, `class`, `name`, `placeholder`, `aria-*`, `data-*`, form actions, linked URLs |
| Embedded JSON | object keys, safe string values, relative and absolute URL values |
| Inline JavaScript | variable names, simple string assignments, object keys, `fetch`/Axios/import URLs |
| Response headers | redirect locations, cookie names and paths, filenames, allowed/exposed header names |
| HTML comments | optional with `--include-comments` |

The tokenizer retains application identifiers and adds useful components:

```text
resetPassword  -> resetPassword, reset, Password
user_profile   -> user_profile, user, profile
report-v2.json -> report-v2.json, report-v2, report, v2, json
```

Candidates are deduplicated, filtered, and sorted before output.

## CLI reference

```text
wordlister (--url URL | --input-file PATH) [OPTIONS]
```

| Option | Purpose | Default |
| --- | --- | --- |
| `--url URL` | Analyze one HTTP/HTTPS target | — |
| `--input-file PATH` | Analyze URLs listed in a UTF-8 text file | — |
| `--threads N` | Concurrent top-level targets | `5` |
| `--min-length N` | Minimum output word length | `1` |
| `--max-length N` | Maximum output word length | `100` |
| `--filter ascii\|unicode` | Character policy | `unicode` |
| `--drop-obfuscated` | Drop hex-like and opaque token values | off |
| `--include-comments` | Include HTML comment candidates | off |
| `--output-format list\|lines` | Machine-readable stdout format | `list` |
| `--connect-timeout SECONDS` | Connection timeout | `3.05` |
| `--read-timeout SECONDS` | Read timeout | `10` |
| `--max-response-bytes N` | Per-response download limit | `2097152` |
| `--max-redirects N` | Same-origin redirect limit | `5` |

`--mode` and `--depth` remain accepted for compatibility with earlier releases, but are deprecated and do not enable crawling.

### Exit codes and streams

| Code | Meaning |
| --- | --- |
| `0` | All selected targets completed |
| `1` | Invalid configuration or unusable input |
| `2` | A wordlist was produced, but one or more targets failed |

Wordlist data is written to **stdout**. Summaries and sanitized warnings are written to **stderr**:

```bash
wordlister --url https://example.com --output-format lines > words.txt
```

## Safety model

- Only exact `http` and `https` schemes are accepted.
- URLs containing embedded credentials are rejected.
- Redirects are limited and restricted to the same origin; a same-host HTTP-to-HTTPS upgrade is allowed.
- Environment proxy and `.netrc` discovery are disabled by default.
- Each response has connect/read timeouts and a decoded body-size limit.
- Contextual secret values and common opaque token formats are excluded where possible.
- Diagnostic URLs omit fragments, credentials, and query values.

Generated wordlists can still contain target-specific business terms and should be handled as assessment artifacts.

## Architecture

```text
CLI
 └── pipeline (deduplication, concurrency, deterministic aggregation)
      ├── HTTP client (validation, redirects, limits, sanitized errors)
      └── response dispatcher
           ├── URL / HTML / JSON / JavaScript / header extractors
           └── tokenizer and final filters
```

The implementation uses a `src/` layout. Extractors are pure functions where possible, while HTTP transport, CLI rendering, and concurrency are isolated. See [`docs/decisions/0001-modular-extraction-pipeline.md`](docs/decisions/0001-modular-extraction-pipeline.md) for the rationale.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

The tests do not require live network access.

## Current limitations

- Wordlister processes the supplied URL or URL list; it is not a recursive crawler.
- External JavaScript and CSS assets are not downloaded for secondary analysis.
- JavaScript extraction is best-effort and does not implement a full parser.
- XML/SVG bodies currently use generic text tokenization.
- The current CLI performs GET requests only.

## Project governance

- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Architecture decisions](docs/decisions/)

## License status

The repository does not currently contain a maintainer-approved license file. Until the copyright holder adds one, no open-source license is asserted by this project metadata.
