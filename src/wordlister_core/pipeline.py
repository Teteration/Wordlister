"""Concurrent orchestration with deterministic output and visible failures."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Protocol

from wordlister_core.errors import FetchError, InvalidTargetError
from wordlister_core.evidence import WordEvidence, score_sources
from wordlister_core.http import sanitize_url, validate_http_url
from wordlister_core.models import (
    ExtractOptions,
    FetchedResponse,
    TargetFailure,
    WordInfo,
    WordlistResult,
)
from wordlister_core.response import extract_response
from wordlister_core.tokenizer import filter_word_counts


class Fetcher(Protocol):
    """Minimal transport contract required by the extraction pipeline."""

    def fetch(self, url: str) -> FetchedResponse: ...


def _process_target(
    target: str,
    fetcher: Fetcher,
    options: ExtractOptions,
) -> WordEvidence:
    response = fetcher.fetch(target)
    candidates = extract_response(
        response,
        include_comments=options.include_comments,
    )
    counts = filter_word_counts(candidates.counts, options)
    return WordEvidence(
        counts=counts,
        sources={word: set(candidates.sources[word]) for word in counts},
    )


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
    word_counts: Counter[str] = Counter()
    word_sources: defaultdict[str, set[str]] = defaultdict(set)
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
                evidence = future.result()
                word_counts.update(evidence.counts)
                for word, sources in evidence.sources.items():
                    word_sources[word].update(sources)
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

    words = tuple(sorted(word_counts))
    return WordlistResult(
        words=words,
        failures=tuple(sorted(failures, key=lambda item: (item.target, item.code))),
        processed_targets=len(valid_targets),
        entries=tuple(
            WordInfo(
                word=word,
                count=word_counts[word],
                score=score_sources(word_sources[word]),
                sources=tuple(sorted(word_sources[word])),
            )
            for word in words
        ),
    )
