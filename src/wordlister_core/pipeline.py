"""Concurrent orchestration with deterministic output and visible failures."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Protocol

from wordlister_core.errors import FetchError, InvalidTargetError
from wordlister_core.http import sanitize_url, validate_http_url
from wordlister_core.models import ExtractOptions, FetchedResponse, TargetFailure, WordlistResult
from wordlister_core.response import extract_response
from wordlister_core.tokenizer import filter_words


class Fetcher(Protocol):
    """Minimal transport contract required by the extraction pipeline."""

    def fetch(self, url: str) -> FetchedResponse: ...


def _process_target(
    target: str,
    fetcher: Fetcher,
    options: ExtractOptions,
) -> set[str]:
    response = fetcher.fetch(target)
    candidates = extract_response(
        response,
        include_comments=options.include_comments,
    )
    return filter_words(candidates, options)


def build_wordlist(
    targets: list[str] | tuple[str, ...],
    *,
    fetcher: Fetcher,
    extract_options: ExtractOptions | None = None,
    workers: int = 5,
) -> WordlistResult:
    """Fetch unique targets and return sorted words plus sanitized failures."""

    if workers < 1:
        raise ValueError("workers must be at least 1")
    options = extract_options or ExtractOptions()
    unique_targets = tuple(dict.fromkeys(target.strip() for target in targets if target.strip()))
    words: set[str] = set()
    failures: list[TargetFailure] = []
    valid_targets: list[str] = []

    for target in unique_targets:
        try:
            validate_http_url(target)
            valid_targets.append(target)
        except InvalidTargetError as error:
            failures.append(
                TargetFailure(
                    target=sanitize_url(target),
                    code="invalid_target",
                    message=str(error),
                )
            )

    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(valid_targets)))) as executor:
        future_targets = {
            executor.submit(_process_target, target, fetcher, options): target
            for target in valid_targets
        }
        for future in as_completed(future_targets):
            target = future_targets[future]
            try:
                words.update(future.result())
            except FetchError as error:
                failures.append(
                    TargetFailure(
                        target=sanitize_url(error.target),
                        code=error.code,
                        message=error.message,
                    )
                )
            except Exception:
                failures.append(
                    TargetFailure(
                        target=sanitize_url(target),
                        code="internal_error",
                        message="target processing failed",
                    )
                )

    return WordlistResult(
        words=tuple(sorted(words)),
        failures=tuple(sorted(failures, key=lambda item: (item.target, item.code))),
        processed_targets=len(valid_targets),
    )
