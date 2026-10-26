"""Occurrence counts and lightweight source provenance for extracted words."""

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class WordEvidence:
    """Mutable extraction result containing counts and unique source labels."""

    counts: Counter[str] = field(default_factory=Counter)
    sources: dict[str, set[str]] = field(default_factory=dict)

    def add(self, words: Counter[str], source: str) -> None:
        """Add counted words attributed to one source label."""

        self.counts.update(words)
        for word, count in words.items():
            if count > 0:
                self.sources.setdefault(word, set()).add(source)

    def update(self, other: "WordEvidence") -> None:
        """Merge another extraction result."""

        self.counts.update(other.counts)
        for word, sources in other.sources.items():
            self.sources.setdefault(word, set()).update(sources)

    def __contains__(self, word: object) -> bool:
        return word in self.counts

    def __getitem__(self, word: str) -> int:
        return self.counts[word]

    def __iter__(self) -> Iterator[str]:
        return iter(self.counts)


SOURCE_WEIGHTS = {
    "form.action": 4,
    "javascript.fetch": 4,
    "javascript.import": 4,
    "javascript.xhr.open": 4,
    "header.location": 3,
    "header.cookie.path": 3,
    "json.url": 3,
    "url.path": 3,
    "url.query.name": 3,
    "url.query.value": 3,
    "url.fragment": 3,
    "html.attribute.name": 2,
    "header.name": 2,
    "header.cookie.name": 2,
    "header.filename": 2,
    "header.value": 2,
    "javascript.declaration": 2,
    "javascript.object_key": 2,
    "json.key": 2,
}


def source_weight(source: str) -> int:
    """Return the documented relevance weight for a source label."""

    if source.startswith("javascript.axios."):
        return 4
    if source.startswith(("html.data-", "html.href", "html.src", "html.poster")):
        return 3
    return SOURCE_WEIGHTS.get(source, 1)


def score_sources(sources: Iterable[str]) -> int:
    """Score a word by summing weights for its unique extraction sources."""

    return sum(source_weight(source) for source in set(sources))
