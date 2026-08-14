# ADR-0010: Model skills as a DAG and plan with topological sort

- **Status:** Accepted
- **Date:** 2026-08-15
- **Phase:** 3

## Context

Phase 2c produces a match score with a list of missing skills. That list is genuinely useful and
still does not answer the question the PRD is built around: *what do I learn first?*

A student missing Kubernetes, Docker, and Linux who starts with Kubernetes wastes weeks. Worse,
a posting that asks for Kubernetes usually never mentions Docker or Linux at all — so the list
of "missing skills" derived from the text is not merely unordered, it is **incomplete**.

Both problems are structural, and both disappear if prerequisite relationships are modelled
explicitly.

## Decision

Skills are **nodes**; a directed edge `A → B` means *A is a prerequisite of B*. The graph is a
**directed acyclic graph**, held in Postgres as `skill_edges` and loaded into a NetworkX
`DiGraph` for traversal.

**Acyclicity is enforced, not assumed.** A cycle means "A requires B requires A" — unlearnable,
and a graph with a cycle has no topological ordering at all. Three layers reject one: a CHECK
constraint kills self-loops, `validate_edges()` runs a colour-marking DFS before the seed
migration inserts anything, and `build_graph()` re-checks at load time.

**Planning algorithm.** Given known skills `K` and required skills `R`:

1. `targets = R - K`
2. `needed = targets ∪ (ancestors of each target) - K` — the transitive closure, which is what
   supplies the prerequisites the posting never named
3. topologically sort the **induced subgraph** on `needed`

**Ties are broken by `(difficulty, name)`** via `lexicographical_topological_sort`. This matters
more than it looks: a DAG usually has *many* valid topological orderings, and plain
`topological_sort` returns an arbitrary one — so the same request could return different advice
on different days. The key makes output deterministic *and* better pedagogy, since among skills
that are equally unblocked it starts with the easier one.

**A separate weighted shortest path** answers a different question: the cheapest single route to
one specific skill, via Dijkstra with edges weighted by the difficulty of the skill being
unlocked. The plan answers "everything I must learn"; the route answers "the most direct way to
this one thing".

## Alternatives considered

- **Set difference (`required - known`).** What Phase 2c already does. Rejected as the *only*
  answer because it cannot order, and cannot infer unstated prerequisites. It remains the right
  answer for the match score, where the question really is "what is missing?"
- **Manual difficulty ordering — sort the missing skills by difficulty and stop.** Cheap, no
  graph, and superficially plausible. Rejected because difficulty is not dependency: Docker
  (3) and Kubernetes (5) happen to sort correctly, while Linux (3) and Docker (3) do not sort
  at all. It would also still miss the unstated prerequisites entirely.
- **Neo4j.** Already rejected in [ADR-0002](0002-technology-stack-selection.md) and nothing here
  changes it: 113 nodes and 128 edges load in milliseconds and fit in memory many times over.
  Cypher would be more expressive; operating a third datastore for a graph this size is not
  justified.
- **Weighted shortest path for the whole plan.** Tempting, since "shortest path" is the phrase
  in the PRD. Wrong tool: a plan is not a path. Reaching Kubernetes needs Docker *and*
  Networking — two branches — and a single path through the DAG cannot express a set of
  requirements that must all be satisfied. Topological sort over the induced subgraph is the
  correct formulation; Dijkstra is kept for the genuinely path-shaped single-skill question.
- **Letting users edit the graph.** Better data eventually, and a moderation problem
  immediately. Deferred.

## Consequences

**Better**

- The output is a *plan*: every step provably appears after everything it depends on, asserted
  by a property test over the real graph.
- Unstated prerequisites surface. A posting naming only Kubernetes yields Linux → Docker →
  Networking → Kubernetes, and each inferred step is flagged `directly_required: false` so the
  user can see what came from the posting and what came from the graph.
- Deterministic: the same inputs always produce the same advice.
- Linear complexity — `O(V + E)` — and imperceptible at this size.

**Worse / accepted**

- **The edge data is the hard part, and it is hand-curated.** Two bad edges were caught during
  this phase by inspecting real output: `embeddings → pgvector` made using a Postgres extension
  require deep learning (a twelve-step plan), and `networking → linux` was simply backwards.
  Neither broke a test that existed at the time — the graph was a perfectly valid DAG in both
  cases. A test now asserts that common targets stay within six steps from scratch, because
  *plausible but wrong* is the failure mode here, not *invalid*.
- **Over-connecting degrades advice silently.** Every added edge lengthens every downstream
  plan. The seed file documents what does not count as a prerequisite (used-together,
  same-category, historically-earlier) precisely because the temptation runs the other way.
- **Difficulty is a guess.** 1–5 per skill, assigned by hand. It only affects tie-breaking and
  effort totals, never correctness of the ordering.
- **The graph is rebuilt per request** — two queries, ~130 edges, a few milliseconds. Caching
  it would be faster but introduces invalidation the moment the vocabulary becomes editable, so
  it waits for a measurement rather than a hunch.
- The graph covers software engineering only. Any other domain produces empty plans until its
  own subgraph is curated.
