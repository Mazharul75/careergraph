"""The skill graph and learning-path search.

Pure graph logic over handwritten fixtures — no database. The last class exercises the real
shipped edge data, because a graph that is correct in the abstract but nonsense in practice is
still nonsense.
"""

from __future__ import annotations

import uuid

import networkx as nx
import pytest

from app.data.skill_edges_seed import (
    SEED_EDGES,
    GraphValidationError,
    validate_edges,
)
from app.data.skills_seed import SEED_SKILLS
from app.services.skill_graph import (
    GraphCycleError,
    GraphSkill,
    LearningPath,
    build_graph,
    compute_learning_path,
    prerequisite_chain,
)


def make_skills(*specs: tuple[str, int]) -> dict[str, GraphSkill]:
    """Build named skills with stable ids, keyed by slug for readable assertions."""
    return {
        slug: GraphSkill(
            skill_id=uuid.uuid5(uuid.NAMESPACE_DNS, slug),
            slug=slug,
            canonical_name=slug.replace("-", " ").title(),
            difficulty=difficulty,
        )
        for slug, difficulty in specs
    }


def graph_of(skills: dict[str, GraphSkill], *edges: tuple[str, str]) -> nx.DiGraph:
    return build_graph(
        list(skills.values()),
        [(skills[a].skill_id, skills[b].skill_id) for a, b in edges],
    )


def names(path: LearningPath) -> list[str]:
    return [step.canonical_name for step in path.steps]


class TestBuildGraph:
    def test_every_skill_becomes_a_node(self) -> None:
        # A skill with no edges is still learnable — dropping isolated nodes would make it
        # impossible to ever recommend.
        skills = make_skills(("python", 2), ("figma", 2))
        graph = graph_of(skills)
        assert graph.number_of_nodes() == 2

    def test_edges_are_directed_prerequisite_to_skill(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3))
        graph = graph_of(skills, ("linux", "docker"))
        assert graph.has_edge(skills["linux"].skill_id, skills["docker"].skill_id)
        assert not graph.has_edge(skills["docker"].skill_id, skills["linux"].skill_id)

    def test_a_cycle_is_rejected(self) -> None:
        # "A requires B requires A" is unlearnable, and no topological ordering exists.
        skills = make_skills(("a", 1), ("b", 1))
        with pytest.raises(GraphCycleError, match="cycle"):
            graph_of(skills, ("a", "b"), ("b", "a"))

    def test_a_longer_cycle_is_rejected(self) -> None:
        skills = make_skills(("a", 1), ("b", 1), ("c", 1))
        with pytest.raises(GraphCycleError):
            graph_of(skills, ("a", "b"), ("b", "c"), ("c", "a"))

    def test_an_edge_to_an_unknown_skill_is_rejected(self) -> None:
        skills = make_skills(("python", 2))
        with pytest.raises(GraphCycleError, match="not in the graph"):
            build_graph(list(skills.values()), [(skills["python"].skill_id, uuid.uuid4())])


class TestLearningPath:
    def test_knowing_everything_yields_an_empty_plan(self) -> None:
        skills = make_skills(("python", 2), ("fastapi", 3))
        graph = graph_of(skills, ("python", "fastapi"))
        path = compute_learning_path(
            graph,
            known=frozenset({skills["python"].skill_id, skills["fastapi"].skill_id}),
            required=frozenset({skills["fastapi"].skill_id}),
        )
        assert path.steps == ()
        assert path.total_effort == 0

    def test_pulls_in_transitive_prerequisites(self) -> None:
        """The central claim: a job asking for Kubernetes also needs Docker and Linux.

        No keyword list contains them, because the posting never mentions them.
        """
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["kubernetes"].skill_id})
        )

        assert names(path) == ["Linux", "Docker", "Kubernetes"]

    def test_prerequisites_already_known_are_skipped(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        path = compute_learning_path(
            graph,
            known=frozenset({skills["linux"].skill_id}),
            required=frozenset({skills["kubernetes"].skill_id}),
        )

        assert names(path) == ["Docker", "Kubernetes"]

    def test_ordering_is_topologically_valid(self) -> None:
        """The property that makes the output a plan rather than a list.

        Every skill must appear after everything it depends on. This is the single most
        important guarantee in the phase.
        """
        skills = make_skills(
            ("html", 1), ("css", 2), ("javascript", 2), ("react", 3), ("nextjs", 3)
        )
        graph = graph_of(
            skills,
            ("html", "css"),
            ("html", "javascript"),
            ("css", "react"),
            ("javascript", "react"),
            ("react", "nextjs"),
        )

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["nextjs"].skill_id})
        )
        position = {step.skill_id: step.order for step in path.steps}

        for step in path.steps:
            for predecessor in graph.predecessors(step.skill_id):
                if predecessor in position:
                    assert position[predecessor] < position[step.skill_id], (
                        f"{step.canonical_name} scheduled before its prerequisite"
                    )

    def test_easier_skills_come_first_among_equals(self) -> None:
        # Both are unblocked from the start, so either order is topologically valid. The
        # difficulty tie-break picks the easier one — better advice, and deterministic.
        skills = make_skills(("hard", 5), ("easy", 1), ("target", 3))
        graph = graph_of(skills, ("hard", "target"), ("easy", "target"))

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["target"].skill_id})
        )
        assert names(path)[:2] == ["Easy", "Hard"]

    def test_output_is_deterministic(self) -> None:
        # A DAG has many valid topological orderings. Without the sort key, the same request
        # could return different advice on different days for no reason.
        skills = make_skills(("a", 2), ("b", 2), ("c", 2), ("target", 3))
        graph = graph_of(skills, ("a", "target"), ("b", "target"), ("c", "target"))
        required = frozenset({skills["target"].skill_id})

        runs = {
            tuple(names(compute_learning_path(graph, known=frozenset(), required=required)))
            for _ in range(5)
        }
        assert len(runs) == 1

    def test_marks_which_skills_the_job_actually_asked_for(self) -> None:
        # "The posting wants Kubernetes" reads very differently from "you need Linux first,
        # even though nobody mentioned it".
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["kubernetes"].skill_id})
        )
        directly = {s.canonical_name for s in path.steps if s.directly_required}

        assert directly == {"Kubernetes"}

    def test_reports_what_unlocks_each_step(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["kubernetes"].skill_id})
        )
        by_name = {s.canonical_name: s.unlocked_by for s in path.steps}

        assert by_name["Linux"] == ()
        assert by_name["Docker"] == ("Linux",)
        assert by_name["Kubernetes"] == ("Docker",)

    def test_total_effort_sums_difficulty(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["kubernetes"].skill_id})
        )
        assert path.total_effort == 11

    def test_multiple_targets_share_prerequisites(self) -> None:
        # Linux is needed by both branches and must appear exactly once.
        skills = make_skills(("linux", 3), ("docker", 3), ("nginx", 3))
        graph = graph_of(skills, ("linux", "docker"), ("linux", "nginx"))

        path = compute_learning_path(
            graph,
            known=frozenset(),
            required=frozenset({skills["docker"].skill_id, skills["nginx"].skill_id}),
        )

        assert names(path).count("Linux") == 1
        assert len(path.steps) == 3

    def test_a_skill_with_no_prerequisites_is_a_one_step_plan(self) -> None:
        skills = make_skills(("figma", 2))
        graph = graph_of(skills)

        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({skills["figma"].skill_id})
        )
        assert names(path) == ["Figma"]

    def test_requirements_outside_the_graph_are_reported(self) -> None:
        # Surfaced rather than silently dropped, so a job naming an unknown skill is visible.
        skills = make_skills(("python", 2))
        graph = graph_of(skills)
        stranger = uuid.uuid4()

        path = compute_learning_path(graph, known=frozenset(), required=frozenset({stranger}))

        assert path.unreachable == (str(stranger),)
        assert path.steps == ()


class TestPrerequisiteChain:
    def test_returns_a_route_to_the_target(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        chain = prerequisite_chain(graph, target=skills["kubernetes"].skill_id, known=frozenset())
        assert chain == ("Linux", "Docker", "Kubernetes")

    def test_starts_from_what_the_user_already_knows(self) -> None:
        skills = make_skills(("linux", 3), ("docker", 3), ("kubernetes", 5))
        graph = graph_of(skills, ("linux", "docker"), ("docker", "kubernetes"))

        chain = prerequisite_chain(
            graph,
            target=skills["kubernetes"].skill_id,
            known=frozenset({skills["docker"].skill_id}),
        )
        assert chain == ("Docker", "Kubernetes")

    def test_prefers_the_cheaper_route(self) -> None:
        # Two routes to the target; the weighted shortest path takes the less effortful one,
        # not the one with fewest hops.
        skills = make_skills(
            ("root", 1), ("cheap-a", 1), ("cheap-b", 1), ("expensive", 5), ("target", 2)
        )
        graph = graph_of(
            skills,
            ("root", "cheap-a"),
            ("cheap-a", "cheap-b"),
            ("cheap-b", "target"),
            ("root", "expensive"),
            ("expensive", "target"),
        )

        chain = prerequisite_chain(graph, target=skills["target"].skill_id, known=frozenset())
        assert "Expensive" not in chain

    def test_a_skill_with_no_prerequisites_is_its_own_chain(self) -> None:
        skills = make_skills(("figma", 2))
        graph = graph_of(skills)
        assert prerequisite_chain(graph, target=skills["figma"].skill_id, known=frozenset()) == (
            "Figma",
        )

    def test_unknown_target_yields_nothing(self) -> None:
        skills = make_skills(("python", 2))
        graph = graph_of(skills)
        assert prerequisite_chain(graph, target=uuid.uuid4(), known=frozenset()) == ()


class TestSeedEdgeValidation:
    def test_the_shipped_edges_validate(self) -> None:
        validate_edges()

    def test_self_loops_are_rejected(self) -> None:
        with pytest.raises(GraphValidationError, match="own prerequisite"):
            validate_edges((("python", "python"),))

    def test_unknown_slugs_are_rejected(self) -> None:
        with pytest.raises(GraphValidationError, match="unknown skills"):
            validate_edges((("python", "cobol"),))

    def test_duplicate_edges_are_rejected(self) -> None:
        with pytest.raises(GraphValidationError, match="Duplicate"):
            validate_edges((("python", "flask"), ("python", "flask")))

    def test_cycles_are_rejected(self) -> None:
        with pytest.raises(GraphValidationError, match="Cycle"):
            validate_edges((("python", "flask"), ("flask", "python")))


class TestShippedGraph:
    """The real vocabulary and the real edges, as deployed."""

    @pytest.fixture
    def graph(self) -> nx.DiGraph:
        by_slug = {
            s.slug: GraphSkill(
                skill_id=uuid.uuid5(uuid.NAMESPACE_DNS, s.slug),
                slug=s.slug,
                canonical_name=s.canonical_name,
                difficulty=s.difficulty,
                category=s.category,
            )
            for s in SEED_SKILLS
        }
        return build_graph(
            list(by_slug.values()),
            [(by_slug[a].skill_id, by_slug[b].skill_id) for a, b in SEED_EDGES],
        )

    def ident(self, slug: str) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_DNS, slug)

    def test_the_shipped_graph_is_a_dag(self, graph: nx.DiGraph) -> None:
        assert nx.is_directed_acyclic_graph(graph)

    def test_every_skill_is_present(self, graph: nx.DiGraph) -> None:
        assert graph.number_of_nodes() == len(SEED_SKILLS)

    def test_kubernetes_pulls_in_its_unstated_prerequisites(self, graph: nx.DiGraph) -> None:
        """A posting asking for Kubernetes never mentions Linux, Docker, or networking.

        All three are genuine prerequisites, and all three are what a keyword list misses.
        """
        path = compute_learning_path(
            graph, known=frozenset(), required=frozenset({self.ident("kubernetes")})
        )
        assert names(path) == ["Linux", "Docker", "Networking", "Kubernetes"]

    def test_paths_stay_short_enough_to_be_useful(self, graph: nx.DiGraph) -> None:
        """Guards the over-connecting failure mode.

        An earlier revision made pgvector depend on deep learning, producing a twelve-step plan
        to use a Postgres extension. Advice that long is advice nobody follows, so the shape of
        the graph is asserted, not just its validity.
        """
        for slug in ("pgvector", "fastapi", "nextjs", "kubernetes", "github-actions"):
            path = compute_learning_path(
                graph, known=frozenset(), required=frozenset({self.ident(slug)})
            )
            assert path.step_count <= 6, f"{slug} needs {path.step_count} steps from scratch"

    def test_a_realistic_gap_produces_a_sensible_plan(self, graph: nx.DiGraph) -> None:
        # A student who knows Python and SQL, applying for a role wanting FastAPI,
        # PostgreSQL and Docker.
        known = frozenset({self.ident("python"), self.ident("sql")})
        required = frozenset(
            {self.ident("fastapi"), self.ident("postgresql"), self.ident("docker")}
        )

        path = compute_learning_path(graph, known=known, required=required)
        ordered = names(path)

        assert "Python" not in ordered  # already known, never re-taught
        assert "Linux" in ordered  # pulled in: Docker needs it, nobody said so
        assert ordered.index("Linux") < ordered.index("Docker")
        assert ordered.index("REST API Design") < ordered.index("FastAPI")

    def test_every_shipped_skill_is_reachable_from_scratch(self, graph: nx.DiGraph) -> None:
        # Every skill must have *some* plan. A skill nobody can be told how to reach is dead
        # weight in the vocabulary.
        for skill in SEED_SKILLS:
            path = compute_learning_path(
                graph, known=frozenset(), required=frozenset({self.ident(skill.slug)})
            )
            assert path.step_count >= 1, f"{skill.slug} has no learning path"
