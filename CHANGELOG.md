# Changelog

All notable changes to this project are documented in this file. The format is based on Keep a Changelog, and releases follow Semantic Versioning.

## [Unreleased]

### Added

- Installable Python package and `wordlister` console command.
- Identifier-aware tokenization and structured URL, HTML, JSON, JavaScript, header, and redirect extraction.
- Configurable HTTP timeouts, response-size limits, and redirect limits.
- Deterministic failure reporting, tests, CI, ADRs, and contributor/security documentation.
- Explicit documentation that no maintainer-approved license file is currently present.

### Changed

- Replaced the monolithic script with a modular `src/wordlister_core` architecture.
- Kept `python3 wordlister.py` as a compatibility launcher.
- Moved summaries and warnings to stderr so stdout remains machine-readable.
- Deprecated the non-functional `--mode` and `--depth` options while retaining compatibility.

### Security

- Reject non-HTTP URL schemes and URLs containing credentials.
- Restrict redirects to the same origin, with same-host HTTP-to-HTTPS upgrades allowed.
- Exclude contextual secret values and common opaque token formats.
- Sanitize diagnostic URLs and bound response downloads.