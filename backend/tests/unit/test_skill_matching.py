"""The skill matcher.

Pure functions over handwritten vocabularies — no database, no seed data — so each test states
exactly the vocabulary it depends on and a failure points at one behaviour.
"""

from __future__ import annotations

import uuid

import pytest

from app.data.skills_seed import SEED_SKILLS, alias_conflicts
from app.services.skill_matching import SkillMatcher, VocabularyEntry


def entry(name: str, *aliases: str, exact_case: bool = False) -> VocabularyEntry:
    return VocabularyEntry(
        skill_id=uuid.uuid4(),
        canonical_name=name,
        terms=(name, *aliases),
        requires_exact_case=exact_case,
    )


def names(matcher: SkillMatcher, text: str) -> list[str]:
    return [m.canonical_name for m in matcher.find(text)]


class TestBasicMatching:
    def test_finds_a_canonical_name(self) -> None:
        matcher = SkillMatcher.build([entry("Python")])
        assert names(matcher, "Experienced with Python") == ["Python"]

    def test_is_case_insensitive_by_default(self) -> None:
        matcher = SkillMatcher.build([entry("Python")])
        assert names(matcher, "python, PYTHON, PyThOn") == ["Python"]

    def test_finds_aliases(self) -> None:
        matcher = SkillMatcher.build([entry("PostgreSQL", "postgres", "psql")])
        assert names(matcher, "Used postgres and psql daily") == ["PostgreSQL"]

    def test_reports_which_terms_matched(self) -> None:
        # Useful for explaining a match back to the user: "we found this because your resume
        # says 'postgres'".
        matcher = SkillMatcher.build([entry("PostgreSQL", "postgres")])
        match = matcher.find("postgres and PostgreSQL")[0]
        assert set(match.matched_terms) == {"postgres", "PostgreSQL"}

    def test_counts_occurrences(self) -> None:
        matcher = SkillMatcher.build([entry("Docker")])
        assert matcher.find("Docker, docker, DOCKER")[0].occurrences == 3

    def test_empty_text_yields_nothing(self) -> None:
        assert SkillMatcher.build([entry("Python")]).find("") == []

    def test_empty_vocabulary_yields_nothing(self) -> None:
        assert SkillMatcher.build([]).find("Python and Docker") == []


class TestWordBoundaries:
    def test_does_not_match_inside_a_longer_word(self) -> None:
        matcher = SkillMatcher.build([entry("Java")])
        assert names(matcher, "JavaBeans and Javanese cuisine") == []

    def test_matches_next_to_punctuation(self) -> None:
        matcher = SkillMatcher.build([entry("Python")])
        assert names(matcher, "Skills: Python, Docker.") == ["Python"]

    def test_matches_at_string_boundaries(self) -> None:
        matcher = SkillMatcher.build([entry("Python")])
        assert names(matcher, "Python") == ["Python"]

    def test_matches_across_newlines(self) -> None:
        matcher = SkillMatcher.build([entry("Redis")])
        assert names(matcher, "Tools\n- Redis\n- Other") == ["Redis"]


class TestPunctuationBearingNames:
    """The cases a naive `\\b` word boundary gets wrong."""

    @pytest.mark.parametrize(
        ("skill", "text"),
        [
            ("C++", "Wrote C++ for embedded systems"),
            ("C++", "Languages: C++, Rust"),
            ("C#", "Built services in C#"),
            (".NET", "Experience with .NET"),
            ("Node.js", "Backend in Node.js"),
            ("Socket.IO", "Realtime with Socket.IO"),
        ],
    )
    def test_matches_names_containing_punctuation(self, skill: str, text: str) -> None:
        # `\bC\+\+\b` never matches: there is no word boundary after `+`.
        assert names(SkillMatcher.build([entry(skill)]), text) == [skill]

    def test_cpp_does_not_match_a_longer_token(self) -> None:
        matcher = SkillMatcher.build([entry("C++")])
        assert names(matcher, "C++11 features") == []

    def test_dotnet_does_not_match_inside_aspdotnet(self) -> None:
        # ".NET" is preceded by "P" in "ASP.NET", which is a word character, so the guard
        # rejects it. ASP.NET is a separate vocabulary entry.
        matcher = SkillMatcher.build([entry(".NET")])
        assert names(matcher, "Built with ASP.NET Core") == []


class TestSubstringCollisions:
    def test_javascript_does_not_yield_java(self) -> None:
        # Leftmost-first alternation with longest-first ordering is what makes this work.
        matcher = SkillMatcher.build([entry("Java"), entry("JavaScript")])
        assert names(matcher, "Strong JavaScript experience") == ["JavaScript"]

    def test_both_are_found_when_both_are_present(self) -> None:
        matcher = SkillMatcher.build([entry("Java"), entry("JavaScript")])
        assert sorted(names(matcher, "Java and JavaScript")) == ["Java", "JavaScript"]

    def test_react_native_beats_react(self) -> None:
        matcher = SkillMatcher.build([entry("React"), entry("React Native")])
        assert names(matcher, "Built apps in React Native") == ["React Native"]

    def test_ordering_of_the_vocabulary_does_not_matter(self) -> None:
        # Guards against a regression where sorting is dropped and results depend on the order
        # rows happen to come back from the database.
        forward = SkillMatcher.build([entry("Java"), entry("JavaScript")])
        reverse = SkillMatcher.build([entry("JavaScript"), entry("Java")])
        assert names(forward, "JavaScript") == names(reverse, "JavaScript") == ["JavaScript"]


class TestExactCaseSkills:
    def test_go_does_not_match_the_english_word(self) -> None:
        matcher = SkillMatcher.build([entry("Go", exact_case=True)])
        assert names(matcher, "willing to go the extra mile") == []

    def test_go_matches_when_capitalised(self) -> None:
        matcher = SkillMatcher.build([entry("Go", exact_case=True)])
        assert names(matcher, "Wrote microservices in Go") == ["Go"]

    def test_r_does_not_match_stray_letters(self) -> None:
        matcher = SkillMatcher.build([entry("R", exact_case=True)])
        assert names(matcher, "r and d, or something") == []

    def test_c_does_not_match_lowercase_c(self) -> None:
        matcher = SkillMatcher.build([entry("C", exact_case=True)])
        assert names(matcher, "a c library") == []

    def test_case_sensitive_aliases_still_work(self) -> None:
        matcher = SkillMatcher.build([entry("Go", "golang")])
        assert names(matcher, "experience with golang") == ["Go"]


class TestOrdering:
    def test_most_mentioned_first(self) -> None:
        matcher = SkillMatcher.build([entry("Python"), entry("Docker")])
        assert names(matcher, "Docker Docker Docker Python") == ["Docker", "Python"]

    def test_ties_break_alphabetically_for_determinism(self) -> None:
        matcher = SkillMatcher.build([entry("Redis"), entry("Docker")])
        assert names(matcher, "Docker and Redis") == ["Docker", "Redis"]


class TestSeedVocabulary:
    """The shipped vocabulary itself, treated as data under test."""

    def test_no_term_is_claimed_by_two_skills(self) -> None:
        # A term mapping to two skills makes extraction nondeterministic. The database has a
        # unique constraint, but this reports *which* terms clash rather than just failing the
        # migration with a unique violation.
        assert alias_conflicts() == {}

    def test_slugs_are_unique_and_lowercase(self) -> None:
        slugs = [s.slug for s in SEED_SKILLS]
        assert len(slugs) == len(set(slugs))
        assert all(slug == slug.lower() for slug in slugs)

    def test_difficulty_is_in_range(self) -> None:
        assert all(1 <= s.difficulty <= 5 for s in SEED_SKILLS)

    def test_ambiguous_names_are_marked_exact_case(self) -> None:
        # If "Go" or "R" ever loses its flag, extraction quality collapses silently — every
        # resume containing the word "go" gains a Go skill.
        by_slug = {s.slug: s for s in SEED_SKILLS}
        for slug in ("go", "r", "c"):
            assert by_slug[slug].exact_case is True, f"{slug} must require exact case"

    def test_the_real_vocabulary_finds_skills_in_a_realistic_resume(self) -> None:
        vocabulary = [
            VocabularyEntry(
                skill_id=uuid.uuid4(),
                canonical_name=s.canonical_name,
                terms=(s.canonical_name, *s.aliases),
                requires_exact_case=s.exact_case,
            )
            for s in SEED_SKILLS
        ]
        resume = """
        Backend engineer. Built REST APIs with FastAPI and Django, backed by Postgres
        and Redis. Containerised everything with Docker and deployed on AWS. Wrote
        unit tests with pytest, set up CI/CD via GitHub Actions. Comfortable with SQL,
        git, and k8s. Some exposure to ML using scikit-learn and pandas.
        """
        found = set(names(SkillMatcher.build(vocabulary), resume))

        for expected in (
            "FastAPI",
            "Django",
            "PostgreSQL",
            "Redis",
            "Docker",
            "AWS",
            "pytest",
            "CI/CD",
            "GitHub Actions",
            "SQL",
            "Git",
            "Kubernetes",
            "Machine Learning",
            "scikit-learn",
            "pandas",
            "REST API Design",
        ):
            assert expected in found, f"expected to find {expected}"

    def test_the_real_vocabulary_does_not_hallucinate(self) -> None:
        vocabulary = [
            VocabularyEntry(
                skill_id=uuid.uuid4(),
                canonical_name=s.canonical_name,
                terms=(s.canonical_name, *s.aliases),
                requires_exact_case=s.exact_case,
            )
            for s in SEED_SKILLS
        ]
        # Deliberately full of English words that collide with skill names.
        prose = "I am willing to go anywhere, or relocate. I care about my work and a lot more."
        assert names(SkillMatcher.build(vocabulary), prose) == []
