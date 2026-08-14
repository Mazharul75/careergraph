"""Match scoring.

Pure functions over handwritten inputs — no database, no model, no embeddings. The scoring
rulebook is the part a user will question ("why is this 62%?"), so it is the part that most
needs to be pinned down by tests.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.embedding import cosine_similarity
from app.services.matching import (
    SEMANTIC_WEIGHT,
    SKILL_WEIGHT,
    RequiredSkill,
    compute_skill_coverage,
    score_match,
)

PY = uuid.uuid4()
DOCKER = uuid.uuid4()
K8S = uuid.uuid4()
RUST = uuid.uuid4()


def req(skill_id: uuid.UUID, name: str, importance: int = 3) -> RequiredSkill:
    return RequiredSkill(skill_id=skill_id, canonical_name=name, importance=importance)


class TestSkillCoverage:
    def test_full_coverage(self) -> None:
        coverage, matched, missing = compute_skill_coverage(
            frozenset({PY, DOCKER}), (req(PY, "Python"), req(DOCKER, "Docker"))
        )
        assert coverage == 1.0
        assert len(matched) == 2
        assert missing == ()

    def test_no_coverage(self) -> None:
        coverage, matched, missing = compute_skill_coverage(frozenset(), (req(PY, "Python"),))
        assert coverage == 0.0
        assert matched == ()
        assert len(missing) == 1

    def test_coverage_is_weighted_by_importance(self) -> None:
        # Holding the skill the job stresses most is worth more than holding a footnote.
        # Candidate has Python (importance 5); missing Docker (importance 1). 5/6, not 1/2.
        coverage, _, _ = compute_skill_coverage(
            frozenset({PY}), (req(PY, "Python", 5), req(DOCKER, "Docker", 1))
        )
        assert coverage == pytest.approx(5 / 6)

    def test_the_reverse_weighting_scores_much_lower(self) -> None:
        coverage, _, _ = compute_skill_coverage(
            frozenset({DOCKER}), (req(PY, "Python", 5), req(DOCKER, "Docker", 1))
        )
        assert coverage == pytest.approx(1 / 6)

    def test_extra_skills_do_not_inflate_the_score(self) -> None:
        # Knowing Rust does not help if the job never asked for it. Coverage is about the
        # job's requirements, not the size of the candidate's skill list.
        coverage, _, _ = compute_skill_coverage(frozenset({PY, RUST, K8S}), (req(PY, "Python"),))
        assert coverage == 1.0

    def test_a_job_with_no_recognised_skills_scores_zero_coverage(self) -> None:
        # Not an error: the semantic component carries the score instead.
        coverage, matched, missing = compute_skill_coverage(frozenset({PY}), ())
        assert (coverage, matched, missing) == (0.0, (), ())

    def test_missing_skills_are_ordered_by_importance(self) -> None:
        # The most consequential gap first — the order a user reads, and the order Phase 3
        # seeds path search from.
        _, _, missing = compute_skill_coverage(
            frozenset(),
            (req(PY, "Python", 2), req(K8S, "Kubernetes", 5), req(DOCKER, "Docker", 3)),
        )
        assert [m.canonical_name for m in missing] == ["Kubernetes", "Docker", "Python"]


class TestScoreMatch:
    def test_perfect_skills_and_perfect_similarity_is_100(self) -> None:
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"),),
            semantic_similarity=1.0,
        )
        assert result.score == 100.0

    def test_components_are_reported_separately(self) -> None:
        # The whole point: a user can see *why*, not just the headline number.
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"), req(DOCKER, "Docker")),
            semantic_similarity=0.5,
        )
        assert result.skill_coverage == 0.5
        assert result.semantic_similarity == 0.5
        assert result.matched[0].canonical_name == "Python"
        assert result.missing[0].canonical_name == "Docker"

    def test_weights_are_applied_as_documented(self) -> None:
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"), req(DOCKER, "Docker")),
            semantic_similarity=1.0,
        )
        expected = (SKILL_WEIGHT * 0.5 + SEMANTIC_WEIGHT * 1.0) * 100
        assert result.score == pytest.approx(expected, abs=0.1)

    def test_skills_outweigh_semantics(self) -> None:
        """A candidate with the skills beats one that merely sounds right.

        This is the design position: semantic similarity corroborates, it does not decide.
        """
        has_skills = score_match(
            user_skill_ids=frozenset({PY, DOCKER}),
            required=(req(PY, "Python"), req(DOCKER, "Docker")),
            semantic_similarity=0.0,
        )
        sounds_right = score_match(
            user_skill_ids=frozenset(),
            required=(req(PY, "Python"), req(DOCKER, "Docker")),
            semantic_similarity=1.0,
        )
        assert has_skills.score > sounds_right.score

    def test_missing_embedding_falls_back_to_skills_only(self) -> None:
        # A resume still parsing should still produce a usable answer.
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"), req(DOCKER, "Docker")),
            semantic_similarity=None,
        )
        assert result.score == 50.0
        assert result.semantic_similarity == 0.0

    def test_negative_similarity_is_clamped(self) -> None:
        # Cosine can go negative; it must not drag the score below what the skills justify.
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"),),
            semantic_similarity=-0.8,
        )
        assert result.semantic_similarity == 0.0
        assert result.score == pytest.approx(SKILL_WEIGHT * 100, abs=0.1)

    def test_score_is_bounded(self) -> None:
        for similarity in (-1.0, 0.0, 0.5, 1.0, 5.0):
            result = score_match(
                user_skill_ids=frozenset({PY}),
                required=(req(PY, "Python"),),
                semantic_similarity=similarity,
            )
            assert 0.0 <= result.score <= 100.0

    def test_total_required_counts_both_sides(self) -> None:
        result = score_match(
            user_skill_ids=frozenset({PY}),
            required=(req(PY, "Python"), req(DOCKER, "Docker"), req(K8S, "Kubernetes")),
        )
        assert result.total_required == 3


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_magnitude_is_ignored(self) -> None:
        # The property that makes cosine the right choice: a long document and a short one
        # saying the same thing still point the same way.
        assert cosine_similarity([1.0, 1.0], [10.0, 10.0]) == pytest.approx(1.0)

    def test_zero_vector_yields_zero_not_a_crash(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_mismatched_dimensions_raise(self) -> None:
        with pytest.raises(ValueError, match="dimensions differ"):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
