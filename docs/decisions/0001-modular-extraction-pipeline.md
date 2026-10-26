# ADR-0001: Use a modular extraction pipeline

## Status

Accepted

## Date

2026-10-26

## Context

The original implementation placed CLI parsing, HTTP requests, concurrency, parsing, filtering, output, and mutable global state in one script. This made extraction policies difficult to test independently, caused inconsistent error behavior, and encouraged new formats to be added as branches in an already mixed control flow.

The repository must remain approachable as a small Python security tool and keep the established `python3 wordlister.py` invocation working.

## Decision

Use a `src/wordlister_core` package with this dependency flow:

```text
CLI -> pipeline -> HTTP client + response dispatcher -> extractors -> tokenizer
```

- Extractors are pure functions wherever practical.
- The HTTP client owns URL validation, redirects, timeouts, size limits, and safe errors.
- The pipeline owns per-run deduplication, concurrency, aggregation, and deterministic ordering.
- The CLI owns argument parsing, rendering, and exit codes.
- `wordlister.py` remains a thin source-checkout launcher.
- The internal package is named `wordlister_core` because a top-level `wordlister.py` module and a `wordlister` package conflict when importing from a source checkout.

## Alternatives considered

### Continue extending the single script

Rejected because each new format would increase coupling and duplicate request/error behavior.

### Introduce a plugin framework

Rejected as premature. The current formats need clear functions and a dispatcher, not runtime discovery or abstract factories.

### Remove the legacy script

Rejected for now because existing users may invoke `python3 wordlister.py`. The launcher preserves compatibility without leaking legacy architecture into the core.

## Consequences

### Positive

- Extraction logic can be tested without network access.
- HTTP policy is consistent for single and file inputs.
- New formats have explicit module boundaries.
- Failures are visible and output remains deterministic.

### Negative

- The project has more files than the original prototype.
- The public project name and internal import package differ.
- Full request-lifecycle changes may span several modules.

## Follow-up

Split an extractor further only when its complexity independently justifies another boundary. Do not add a crawler module until recursive crawling is intentionally designed and tested.