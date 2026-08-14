"""Match scoring: how well does a profile fit a job?

Two independent signals, combined and always reported separately:

**Skill coverage** — of the skills this job requires, how many does the candidate have, weighted
by how much each matters? Precise, explainable, and directly actionable: the missing ones *are*
the learning plan (Phase 3 orders them).

**Semantic similarity** — cosine similarity between the resume text and the job description.
Catches everything the vocabulary misses: phrasing, seniority, domain, responsibilities no
skill list captures.

Neither alone is enough. Skill coverage is blind to a resume that describes the right work in
words the vocabulary does not contain. Semantic similarity is confidently vague — it produces a
number nobody can act on, and it will happily rate a plausible-sounding but unqualified
candidate highly.

The score is deliberately **explainable**: every response carries the matched skills, the
missing skills, and both component scores. An unexplained 73% is not actionable, and users
(rightly) do not trust it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# Skill coverage is weighted higher than semantic similarity. Two reasons: it is the signal a
# user can act on, and it is the one we can defend line by line. Semantic similarity is a
# useful corroborator, not a verdict.
SKILL_WEIGHT = 0.65
SEMANTIC_WEIGHT = 0.35


@dataclass(frozen=True, slots=True)
class SkillGap:
    skill_id: uuid.UUID
    canonical_name: str
    importance: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A score with its full reasoning attached."""

    score: float  # 0-100, the headline number
    skill_coverage: float  # 0-1, importance-weighted
    semantic_similarity: float  # 0-1, cosine
    matched: tuple[SkillGap, ...]
    missing: tuple[SkillGap, ...]

    @property
    def total_required(self) -> int:
        return len(self.matched) + len(self.missing)


@dataclass(frozen=True, slots=True)
class RequiredSkill:
    skill_id: uuid.UUID
    canonical_name: str
    importance: int = 3


@dataclass(frozen=True, slots=True)
class MatchInputs:
    """Everything scoring needs, with no ORM types.

    Keeping this a plain dataclass is what lets the whole scoring rulebook be unit-tested with
    handwritten inputs and no database.
    """

    user_skill_ids: frozenset[uuid.UUID]
    required: tuple[RequiredSkill, ...]
    resume_embedding: list[float] | None = None
    job_embedding: list[float] | None = None


def compute_skill_coverage(
    user_skill_ids: frozenset[uuid.UUID], required: tuple[RequiredSkill, ...]
) -> tuple[float, tuple[SkillGap, ...], tuple[SkillGap, ...]]:
    """Importance-weighted fraction of required skills the candidate holds.

    Weighted, not a plain count: missing one skill the job names five times is not the same as
    missing one it mentions in passing. Weighting by importance makes the score reflect what the
    employer actually emphasised.
    """
    if not required:
        # A job with no recognised skills cannot be scored on coverage. Returning 0.0 would
        # unfairly punish every candidate; the semantic component carries the score instead.
        return 0.0, (), ()

    matched: list[SkillGap] = []
    missing: list[SkillGap] = []
    for skill in required:
        gap = SkillGap(skill.skill_id, skill.canonical_name, skill.importance)
        (matched if skill.skill_id in user_skill_ids else missing).append(gap)

    total_weight = sum(s.importance for s in required)
    matched_weight = sum(s.importance for s in matched)
    coverage = matched_weight / total_weight if total_weight else 0.0

    # Missing skills sorted by importance: the most consequential gap first, which is the order
    # a user wants to read and the order Phase 3 seeds its path search from.
    missing.sort(key=lambda s: (-s.importance, s.canonical_name))
    matched.sort(key=lambda s: (-s.importance, s.canonical_name))
    return coverage, tuple(matched), tuple(missing)


def score_match(
    *,
    user_skill_ids: frozenset[uuid.UUID],
    required: tuple[RequiredSkill, ...],
    semantic_similarity: float | None = None,
) -> MatchResult:
    """Combine both signals into a 0-100 score.

    When no embedding is available yet — a resume still parsing, a job whose embedding job has
    not run — the skill component carries the whole score rather than the result being withheld.
    A partial answer now beats a perfect answer after a page refresh.
    """
    coverage, matched, missing = compute_skill_coverage(user_skill_ids, required)

    if semantic_similarity is None:
        combined = coverage
        similarity = 0.0
    else:
        # Cosine can be negative; clamp so a below-zero similarity cannot drag the score under
        # what the skill evidence alone justifies.
        similarity = max(0.0, min(1.0, semantic_similarity))
        combined = SKILL_WEIGHT * coverage + SEMANTIC_WEIGHT * similarity

    return MatchResult(
        score=round(combined * 100, 1),
        skill_coverage=round(coverage, 4),
        semantic_similarity=round(similarity, 4),
        matched=matched,
        missing=missing,
    )
