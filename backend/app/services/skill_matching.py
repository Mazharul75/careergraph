"""Skill extraction from free text.

Rule-based information extraction over a curated vocabulary — not statistical NLP, and worth
being precise about that. For a closed vocabulary of a few hundred known technologies, exact
matching over curated aliases is *more* accurate than a general-purpose NER model, because the
answer set is finite and enumerable. The semantic layer arrives in Phase 2c with embeddings,
where the open-ended question ("how similar are these two documents?") actually needs one.

Pure functions over plain dataclasses. No database, no ORM — the vocabulary is passed in — so
the whole module unit-tests in milliseconds and runs identically in the API and the worker.

Three things make this harder than `if skill in text`:

1. **Punctuation-bearing names.** `C++`, `C#`, `.NET`, `Node.js`, `Socket.IO`. A naive `\\b`
   word boundary fails on all of them: `\\bC++\\b` never matches, because there is no word
   boundary after `+`.
2. **Substring collisions.** `Java` is inside `JavaScript`; `React` is inside `React Native`.
   Matching the short one first silently mislabels the long one.
3. **Ordinary English words.** `Go`, `R`, `C`, `D`, `Rust` are real skills and also real words.
   Case-insensitive matching fires on "go to", "or", "a c library" — noise that would poison
   every downstream score.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """One skill and every string that should resolve to it."""

    skill_id: uuid.UUID
    canonical_name: str
    terms: tuple[str, ...]  # canonical name plus aliases
    requires_exact_case: bool = False


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill_id: uuid.UUID
    canonical_name: str
    matched_terms: tuple[str, ...]
    occurrences: int


# Characters that count as "part of a word" for boundary purposes. Deliberately excludes
# `+`, `#`, `.`, and `-`, so `C++` can end at the `+` and `.NET` can begin at the `.`.
_WORD_CHAR = r"[A-Za-z0-9_]"
_PREFIX_GUARD = rf"(?<!{_WORD_CHAR})"
_SUFFIX_GUARD = rf"(?!{_WORD_CHAR})"


def _pattern_for(terms: list[str]) -> re.Pattern[str] | None:
    """Compile one alternation over all terms, longest first.

    Longest-first ordering is what resolves substring collisions. Python's regex alternation is
    leftmost-first, not leftmost-longest: at a given position it takes the first branch that
    matches. With `JavaScript` ahead of `Java`, the text "JavaScript" yields JavaScript. In the
    other order it would yield Java and leave "Script" behind.
    """
    if not terms:
        return None

    ordered = sorted(set(terms), key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in ordered)
    return re.compile(f"{_PREFIX_GUARD}(?:{alternation}){_SUFFIX_GUARD}")


@dataclass(slots=True)
class SkillMatcher:
    """Compiled vocabulary, reusable across many documents.

    Compilation is the expensive part, so it happens once and the matcher is reused — in the
    worker, that means once per task rather than once per resume section.
    """

    _lookup: dict[str, VocabularyEntry] = field(default_factory=dict)
    _exact_lookup: dict[str, VocabularyEntry] = field(default_factory=dict)
    _insensitive: re.Pattern[str] | None = None
    _sensitive: re.Pattern[str] | None = None

    @classmethod
    def build(cls, vocabulary: list[VocabularyEntry]) -> SkillMatcher:
        matcher = cls()
        insensitive_terms: list[str] = []
        sensitive_terms: list[str] = []

        for entry in vocabulary:
            for term in entry.terms:
                cleaned = term.strip()
                if not cleaned:
                    continue
                if entry.requires_exact_case:
                    matcher._exact_lookup[cleaned] = entry
                    sensitive_terms.append(cleaned)
                else:
                    # Keyed lowercase so a case-insensitive hit can be mapped back regardless
                    # of how it was capitalised in the document.
                    matcher._lookup[cleaned.lower()] = entry
                    insensitive_terms.append(cleaned)

        pattern = _pattern_for(insensitive_terms)
        matcher._insensitive = (
            re.compile(pattern.pattern, re.IGNORECASE) if pattern is not None else None
        )
        matcher._sensitive = _pattern_for(sensitive_terms)
        return matcher

    def find(self, text: str) -> list[SkillMatch]:
        """Return every skill mentioned, with occurrence counts.

        Results are ordered by occurrences descending, then name, so output is deterministic —
        a test that asserts on ordering should not flake, and the UI gets a sensible default
        ranking for free.
        """
        if not text:
            return []

        hits: dict[uuid.UUID, tuple[VocabularyEntry, set[str], int]] = {}

        def record(entry: VocabularyEntry, matched: str) -> None:
            existing = hits.get(entry.skill_id)
            if existing is None:
                hits[entry.skill_id] = (entry, {matched}, 1)
            else:
                _entry, terms, count = existing
                terms.add(matched)
                hits[entry.skill_id] = (_entry, terms, count + 1)

        if self._insensitive is not None:
            for match in self._insensitive.finditer(text):
                entry = self._lookup.get(match.group(0).lower())
                if entry is not None:
                    record(entry, match.group(0))

        if self._sensitive is not None:
            for match in self._sensitive.finditer(text):
                entry = self._exact_lookup.get(match.group(0))
                if entry is not None:
                    record(entry, match.group(0))

        return sorted(
            (
                SkillMatch(
                    skill_id=entry.skill_id,
                    canonical_name=entry.canonical_name,
                    matched_terms=tuple(sorted(terms)),
                    occurrences=count,
                )
                for entry, terms, count in hits.values()
            ),
            key=lambda m: (-m.occurrences, m.canonical_name),
        )
