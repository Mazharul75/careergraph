"""The skill-dependency graph and learning-path search.

This is the product's differentiator, so it is worth being precise about the graph theory.

## The model

Skills are **nodes**. A directed edge `A → B` means *A is a prerequisite of B*. The graph is a
**DAG** — directed and acyclic — and acyclicity is not a nicety: a cycle would mean "A requires
B requires A", which is unlearnable, and a topological ordering of a cyclic graph does not
exist. `build_graph` rejects cycles rather than producing nonsense.

## Why a graph rather than a set difference

Set difference answers "what am I missing?" — an unordered pile. It cannot answer "what do I
learn *first*?", and that ordering is the entire product. Two things fall out of the graph that
a list cannot give:

**Transitive prerequisites.** A job requiring Kubernetes needs Docker and Linux too, even
though the posting never mentions them. That is `ancestors(Kubernetes)`, and no keyword list
contains it.

**A valid order.** A topological sort produces a sequence where every skill appears after
everything it depends on. That property is what makes the output a *plan*.

## The algorithm

Given known skills `K` and a job's required skills `R`:

1. `targets` = the required skills not yet held: `R` minus `K`.
2. `needed` = those targets, plus the union of `ancestors(t)` for every target, minus `K`.
   Every transitive prerequisite the user also lacks. This is the step a flat list cannot do.
3. Take the **induced subgraph** on `needed` and topologically sort it.
4. Break ties by `(difficulty, name)` using a lexicographic topological sort, so easier
   foundations come first and the output is deterministic.

Complexity is `O(V + E)` for the sort and `O(V + E)` per ancestor query — linear, and on 113
nodes it is measured in microseconds.

## Why the tie-break matters

A DAG usually has *many* valid topological orderings. Plain `topological_sort` returns an
arbitrary one, which means the advice could change between requests for no reason. Sorting ties
by estimated difficulty produces a stable order that also happens to be good pedagogy: when two
skills are equally unblocked, start with the easier one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import networkx as nx


class GraphCycleError(Exception):
    """The edges contain a cycle, so no learning order exists."""


@dataclass(frozen=True, slots=True)
class GraphSkill:
    """A node, free of ORM types so the graph can be built and tested without a database."""

    skill_id: uuid.UUID
    slug: str
    canonical_name: str
    difficulty: int
    category: str = ""


@dataclass(frozen=True, slots=True)
class PathStep:
    """One skill in a learning plan."""

    skill_id: uuid.UUID
    slug: str
    canonical_name: str
    difficulty: int
    order: int
    #: True when the job explicitly asked for this skill; False when it was pulled in as a
    #: prerequisite. The distinction matters to a user: "the posting wants Kubernetes" reads
    #: very differently from "you need Linux first, even though nobody mentioned it".
    directly_required: bool
    #: Prerequisites of this step that are also in the plan — what unlocks it.
    unlocked_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LearningPath:
    steps: tuple[PathStep, ...]
    total_effort: int
    #: Required skills that are unreachable because a prerequisite is missing from the graph
    #: entirely. Empty in practice; surfaced rather than silently dropped.
    unreachable: tuple[str, ...] = ()

    @property
    def step_count(self) -> int:
        return len(self.steps)


def build_graph(skills: list[GraphSkill], edges: list[tuple[uuid.UUID, uuid.UUID]]) -> nx.DiGraph:
    """Assemble the DAG, rejecting cycles.

    Every skill becomes a node even if it has no edges: a skill with no prerequisites is a
    perfectly good starting point, and dropping isolated nodes would make them unlearnable.
    """
    graph: nx.DiGraph = nx.DiGraph()
    for skill in skills:
        graph.add_node(
            skill.skill_id,
            slug=skill.slug,
            canonical_name=skill.canonical_name,
            difficulty=skill.difficulty,
            category=skill.category,
        )

    for prerequisite_id, skill_id in edges:
        # Silently skipping unknown endpoints would hide a broken edge. The seed migration
        # validates referential integrity, and the database has foreign keys, so reaching here
        # with a dangling edge means something is genuinely wrong.
        if prerequisite_id not in graph or skill_id not in graph:
            raise GraphCycleError(
                f"Edge references a skill not in the graph: {prerequisite_id} -> {skill_id}"
            )
        graph.add_edge(prerequisite_id, skill_id)

    if not nx.is_directed_acyclic_graph(graph):
        cycle = nx.find_cycle(graph)
        names = [graph.nodes[u]["canonical_name"] for u, _v, *_ in cycle]
        raise GraphCycleError(f"Prerequisite cycle: {' -> '.join(names)}")

    return graph


def compute_learning_path(
    graph: nx.DiGraph,
    *,
    known: frozenset[uuid.UUID],
    required: frozenset[uuid.UUID],
) -> LearningPath:
    """Produce an ordered plan from what the user knows to what the job needs."""
    # Requirements the graph has never heard of cannot be planned for. Report them rather than
    # dropping them, so a job naming a skill outside the vocabulary is visible, not invisible.
    unreachable = tuple(sorted(str(skill_id) for skill_id in required if skill_id not in graph))
    targets = {s for s in required if s in graph and s not in known}

    if not targets:
        return LearningPath(steps=(), total_effort=0, unreachable=unreachable)

    # Step 2: transitive prerequisites the user also lacks. `ancestors` is the whole reason a
    # graph beats a list — a posting asking for Kubernetes never mentions Linux.
    needed: set[uuid.UUID] = set(targets)
    for target in targets:
        needed |= nx.ancestors(graph, target) - known

    subgraph = graph.subgraph(needed)

    # Lexicographic topological sort, keyed by (difficulty, name). A DAG has many valid
    # orderings; plain topological_sort picks an arbitrary one, so the same request could
    # return different advice on different days. The key makes it deterministic *and* good
    # pedagogy: among skills that are equally unblocked, do the easier one first.
    def sort_key(node: uuid.UUID) -> tuple[int, str]:
        data = graph.nodes[node]
        return (data["difficulty"], data["canonical_name"])

    ordered = list(nx.lexicographical_topological_sort(subgraph, key=sort_key))

    steps: list[PathStep] = []
    for index, node in enumerate(ordered, start=1):
        data = graph.nodes[node]
        # Predecessors within the plan: what the user must finish before starting this one.
        unlocked_by = tuple(
            sorted(graph.nodes[p]["canonical_name"] for p in subgraph.predecessors(node))
        )
        steps.append(
            PathStep(
                skill_id=node,
                slug=data["slug"],
                canonical_name=data["canonical_name"],
                difficulty=data["difficulty"],
                order=index,
                directly_required=node in targets,
                unlocked_by=unlocked_by,
            )
        )

    return LearningPath(
        steps=tuple(steps),
        total_effort=sum(step.difficulty for step in steps),
        unreachable=unreachable,
    )


def prerequisite_chain(
    graph: nx.DiGraph, *, target: uuid.UUID, known: frozenset[uuid.UUID]
) -> tuple[str, ...]:
    """The cheapest single chain from something already known to `target`.

    A genuine shortest-path query, distinct from the full plan above. The plan answers "what is
    everything I must learn?"; this answers "what is the most direct route to this one skill?"
    — the thing a user asks when they only care about one item on the list.

    Edges are weighted by the *difficulty of the skill being unlocked*, so the cheapest route is
    the one requiring least total learning effort, not the one with fewest hops.
    """
    if target not in graph:
        return ()

    ancestors = nx.ancestors(graph, target)
    # Entry points: skills already known that lead to the target, or roots of its ancestry if
    # the user knows nothing relevant.
    sources = {a for a in ancestors if a in known} or {
        a for a in ancestors if graph.in_degree(a) == 0
    }
    if not sources:
        return (graph.nodes[target]["canonical_name"],)

    def weight(_u: uuid.UUID, v: uuid.UUID, _data: dict) -> int:
        return int(graph.nodes[v]["difficulty"])

    best: list[uuid.UUID] | None = None
    best_cost = float("inf")
    for source in sources:
        try:
            # With an explicit `target`, dijkstra returns a single (cost, path) pair rather
            # than the per-node mappings it produces when target is omitted.
            cost_raw, path_raw = nx.single_source_dijkstra(graph, source, target, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        # With an explicit `target`, dijkstra returns one (cost, path) pair rather than the
        # per-node mappings it produces when target is omitted; the annotation covers both.
        cost = float(cost_raw)  # type: ignore[arg-type]
        if cost < best_cost:
            best_cost = cost
            best = list(path_raw)

    if best is None:
        return (graph.nodes[target]["canonical_name"],)
    return tuple(graph.nodes[n]["canonical_name"] for n in best)
