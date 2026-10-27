# Wordlister

[![CI](https://github.com/Teteration/Wordlister/actions/workflows/ci.yml/badge.svg)](https://github.com/Teteration/Wordlister/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

Wordlister builds **target-specific wordlists** from URLs and bounded HTTP responses. It is designed for authorized reconnaissance and fuzzing workflows where generic dictionaries miss application-specific routes, parameters, field names, and identifiers.

It does not ship with a dictionary and does not download third-party wordlists. Every output candidate comes from the targets you provide.

> Use Wordlister only against systems you own or are explicitly authorized to test.

## Highlights

- Extracts backend-oriented route segments, query parameter names, and nested URL routes.
- Splits `camelCase`, `PascalCase`, `snake_case`, `kebab-case`, dotted names, and mixed identifiers while retaining useful originals.
- Extracts backend-oriented form fields, endpoint references, request parameters, and optional comments from HTML and JavaScript.
- Parses JSON keys and URL-shaped values recursively with depth and node limits.
- Extracts selected response-header metadata and redirect paths without emitting cookie or authorization values.
- Optionally delegates URL discovery to `hakrawler` while retaining Wordlister's own validation, scope, fetch, extraction, and scoring policies.
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

Recursive discovery is optional and requires the separate `hakrawler` executable:

```bash
go install github.com/hakluke/hakrawler@latest
```

Ensure the Go binary directory, commonly `~/go/bin`, is present in `PATH`. Wordlister does not download or install crawler binaries automatically.

## Quick start

```bash
wordlister --url https://example.com --output-format lines
```

Or run directly from the repository:

```bash
python3 wordlister.py --url https://example.com --output-format lines
```

Discover same-host URLs through five link layers with `hakrawler`, then let Wordlister fetch and analyze the bounded result set:

```bash
wordlister \
  --url https://example.com \
  --crawler hakrawler \
  --mode domain \
  --depth 5 \
  --max-pages 1000 \
  --output-format json | jq .
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
| Requested, redirected, and final URLs | route segments, query parameter names, and nested URL routes |
| HTML forms and endpoint attributes | field names, form actions, navigational links, iframe URLs, and explicit `data-api`/`data-endpoint`/`data-url` references |
| Embedded JSON | object keys and relative or absolute URL values |
| Inline JavaScript | request URLs and parameters in request payloads, `FormData`, and `URLSearchParams` |
| Response headers | redirect routes, cookie names and paths, and CORS-allowed request-header names |
| HTML comments | optional with `--include-comments` |

The tokenizer retains application identifiers and adds useful components:

```text
resetPassword  -> resetPassword, reset, Password
user_profile   -> user_profile, user, profile
report-v2.json -> report-v2.json, report-v2, report, v2, json
```

Candidates are deduplicated, filtered, and sorted before output.
Candidates containing Persian or other Arabic-script letters are discarded, including mixed identifiers, because they are unlikely to be backend parameter names in the intended fuzzing workflow. Other Unicode scripts remain subject to the selected `--filter` policy.

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
| `--output-format list\|lines\|json` | Machine-readable stdout format | `list` |
| `--crawler none\|hakrawler` | Optional external URL discovery provider | `none` |
| `--mode single\|domain\|subdomain` | Discovery scope | `domain` |
| `--depth N` | Maximum discovered-link depth; requires `--crawler hakrawler` | `0` |
| `--max-pages N` | Maximum pages Wordlister fetches per supplied seed after discovery | `1000` |
| `--crawler-timeout SECONDS` | Maximum hakrawler runtime per supplied seed | `120` |
| `--crawler-path PATH` | Custom hakrawler executable name or path | `hakrawler` |
| `--connect-timeout SECONDS` | Connection timeout | `3.05` |
| `--read-timeout SECONDS` | Read timeout | `10` |
| `--max-response-bytes N` | Per-response download limit | `2097152` |
| `--max-redirects N` | Same-origin redirect limit | `5` |

Without `--crawler hakrawler`, Wordlister processes only the supplied URL or URL list. Giving a positive `--depth` without selecting a crawler is an error rather than silently ignoring the option.

Depth is measured in discovered-link hops: depth `1` includes links found on the seed, depth `2` includes links found on those pages, and so on. `single` disables discovery, `domain` permits only the exact seed host, and `subdomain` also permits child subdomains. Wordlister independently validates and normalizes crawler output, removes fragments and common static/download assets, reapplies scope, deduplicates URLs, and enforces the per-seed `--max-pages` fetch budget.

Discovery and extraction are separate network stages: hakrawler fetches pages to discover URLs, then Wordlister fetches the selected URLs again with its own bounded HTTP client to extract and score candidates. This intentionally duplicates requests for selected pages so crawler-specific transport behavior cannot bypass Wordlister's extraction and HTTP policies. The crawler timeout, depth, response-size setting, and Wordlister page budget should therefore be chosen conservatively.

Wordlister starts hakrawler with redirect following disabled so an unvalidated redirect cannot silently move discovery to another origin. Supply the final canonical seed URL (for example, the post-redirect HTTPS or `www` URL) when discovery returns no links from a redirecting seed.

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

To include each word's total count, source-based score, and provenance labels:

```bash
wordlister --url https://example.com --output-format json | jq .
```

```json
{
  "resetPassword": {
    "score": 10,
    "sources": [
      "form.action",
      "javascript.fetch",
      "json.key"
    ],
    "count": 4
  }
}
```

The `json` format is valid UTF-8 JSON on stdout and can be processed directly with `jq`. Summaries and warnings remain on stderr.

`count` is the total number of extracted occurrences. `sources` contains unique, sorted extraction contexts such as `form.action`, `javascript.fetch`, and `json.key`. `score` is calculated from unique sources, not repetition count. For example, `form.action` (4) + `javascript.fetch` (4) + `json.key` (2) produces a score of 10.

### Source provenance labels

The current fixed source labels are:

| Area | Sources |
| --- | --- |
| URL | `url.path`, `url.query.name`, `url.query.url` |
| HTML | `html.comment` (opt-in), `form.field.name`, `form.action`, `html.formaction`, `html.href`, `html.src`, `html.data-api`, `html.data-endpoint`, `html.data-href`, `html.data-url` |
| JSON | `json.key`, `json.url` |
| JavaScript | `javascript.url`, `javascript.parameter`, `javascript.fetch`, `javascript.xhr.open`, `javascript.axios.get`, `javascript.axios.post`, `javascript.axios.put`, `javascript.axios.patch`, `javascript.axios.delete` |
| Response headers | `header.location`, `header.cookie.name`, `header.cookie.path`, `header.value` |

Source weights are 4 for form field names, query names, cookie names, CORS-allowed request-header names, explicit form/data endpoints, and JavaScript request parameters or destinations; 3 for other route-like URL sources; 2 for JSON keys; and 1 for optional comment sources. Each unique source contributes its weight at most once per word.

Visible HTML prose, `class`/`id`/presentation attributes, arbitrary JSON string values, generic JavaScript variable names, host labels, fragments, static image/script assets, and generic response-header names are not extracted. They tend to describe the frontend rather than accepted backend input.

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
 ├── optional discovery adapter (hakrawler subprocess)
 │    └── validation, scope enforcement, normalization, asset filtering, page budget
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

The normal test suite uses mocked subprocesses and does not require hakrawler or live network access.

## Current limitations

- Recursive discovery requires a separately installed `hakrawler` executable and does not execute browser JavaScript.
- Routes that only appear after client-side JavaScript execution may not be discovered.
- `--max-pages` limits Wordlister's post-discovery fetches; hakrawler itself is bounded by depth, page-size, and crawler-timeout settings rather than a native page-count flag.
- External JavaScript and CSS assets are not downloaded for secondary analysis.
- JavaScript extraction is best-effort and does not implement a full parser.
- The current CLI performs GET requests only.

## Project governance

- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Architecture decisions](docs/decisions/)

## License status

The repository does not currently contain a maintainer-approved license file. Until the copyright holder adds one, no open-source license is asserted by this project metadata.
