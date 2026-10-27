# Changelog

All notable changes to this project are documented in this file. The format is based on Keep a Changelog, and releases follow Semantic Versioning.

## [Unreleased]

### Added

- Installable Python package and `wordlister` console command.
- Identifier-aware tokenization and structured URL, HTML, JSON, JavaScript, header, and redirect extraction.
- Configurable HTTP timeouts, response-size limits, and redirect limits.
- Deterministic failure reporting, tests, CI, ADRs, and contributor/security documentation.
- Explicit documentation that no maintainer-approved license file is currently present.
- Per-word occurrence counts, source provenance, source-based relevance scores, and JSON output suitable for `jq`.
- Optional `hakrawler` URL discovery with explicit depth, scope, timeout, and Wordlister fetch-budget controls.
- Mocked discovery-provider tests that do not require a local hakrawler installation or public network access.

### Changed

- Replaced the monolithic script with a modular `src/wordlister_core` architecture.
- Kept `python3 wordlister.py` as a compatibility launcher.
- Moved summaries and warnings to stderr so stdout remains machine-readable.
- Replaced silently ignored crawl arguments with an explicit `--crawler hakrawler` integration; positive depth without a selected crawler now fails clearly.
- Removed low-signal visible HTML and unstructured response text from extraction.
- Focused default extraction on backend routes and input names, excluding presentation attributes, generic JSON/JavaScript values, host labels, fragments, static assets, and generic response-header metadata.
- Dropped candidates containing Persian or other Arabic-script letters, including mixed identifiers.
- Kept discovery and extraction as separate network stages, so Wordlister refetches selected crawler results under its own HTTP policy.

### Security

- Reject non-HTTP URL schemes and URLs containing credentials.
- Restrict redirects to the same origin, with same-host HTTP-to-HTTPS upgrades allowed.
- Exclude contextual secret values and common opaque token formats.
- Sanitize diagnostic URLs and bound response downloads.
- Run external discovery without a shell, inherited proxy settings, or unbounded captured output; revalidate every returned URL before fetching it.