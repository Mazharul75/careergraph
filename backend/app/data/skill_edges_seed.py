"""Prerequisite edges — the skill-dependency graph.

Each entry is ``(prerequisite_slug, skill_slug)``, read as **"you should learn the first before
the second."** These edges are the entire reason this project produces an *ordered* plan rather
than an unordered pile of missing keywords.

## What counts as a prerequisite

Only a genuine learning dependency: attempting the second skill without the first means not
understanding what you are doing, rather than merely finding it harder. Kubernetes without
Docker is memorising commands; Docker without Linux is memorising commands.

Deliberately **not** edges:

* *Commonly used together.* React and Tailwind appear in the same job constantly and neither
  teaches the other.
* *Same category.* PostgreSQL and MongoDB are both databases and neither is a prerequisite.
* *Historically earlier.* C came before Rust; that is not a learning dependency.

Over-connecting is the failure mode to guard against. A dense graph makes every learning path
absurdly long ("to learn React, first learn C") and the advice becomes useless.

## The graph must be acyclic

A cycle means "A requires B requires A" — unlearnable, and a topological sort of it does not
exist. `validate_edges()` below rejects cycles, and the seed migration runs it, so a bad edge
fails the migration rather than producing nonsense at runtime.
"""

from __future__ import annotations

from app.data.skills_seed import SEED_SKILLS

# fmt: off
SEED_EDGES: tuple[tuple[str, str], ...] = (
    # --- Programming foundations ------------------------------------------------------
    ("data-structures", "algorithms"),
    ("algorithms", "graph-theory"),
    ("python", "oop"),
    ("oop", "java"),
    ("oop", "c-sharp"),
    ("c", "cpp"),
    ("data-structures", "c"),

    # --- Python ecosystem --------------------------------------------------------------
    ("python", "flask"),
    ("python", "django"),
    ("python", "fastapi"),
    ("flask", "fastapi"),          # Flask is the gentler introduction to the same ideas
    ("python", "pytest"),
    ("python", "pandas"),
    ("python", "numpy"),
    ("python", "celery"),
    ("python", "sqlalchemy"),
    ("sql", "sqlalchemy"),
    ("concurrency", "celery"),
    ("python", "concurrency"),

    # --- Web fundamentals ---------------------------------------------------------------
    ("html", "css"),
    ("css", "responsive-design"),
    ("css", "tailwind"),
    ("html", "accessibility"),
    ("javascript", "typescript"),
    ("html", "javascript"),
    ("rest-api", "graphql"),
    ("rest-api", "api-documentation"),
    ("networking", "rest-api"),

    # --- Frontend ----------------------------------------------------------------------
    ("javascript", "react"),
    ("css", "react"),
    ("react", "nextjs"),
    ("react", "react-native"),
    ("react", "redux"),
    ("javascript", "vue"),
    ("typescript", "angular"),
    ("javascript", "svelte"),
    ("javascript", "jest"),
    ("typescript", "playwright"),

    # --- Backend frameworks ------------------------------------------------------------
    ("javascript", "express"),
    ("typescript", "nestjs"),
    ("express", "nestjs"),
    ("java", "spring-boot"),
    ("c-sharp", "dotnet"),
    ("ruby", "rails"),
    ("php", "laravel"),
    ("rest-api", "fastapi"),
    ("rest-api", "django"),
    ("rest-api", "express"),

    # --- Databases ---------------------------------------------------------------------
    ("sql", "postgresql"),
    ("sql", "mysql"),
    ("sql", "sqlite"),
    ("sql", "database-design"),
    ("database-design", "postgresql"),
    ("postgresql", "pgvector"),
    ("database-design", "mongodb"),
    ("sql", "prisma"),
    ("database-design", "cassandra"),
    ("graph-theory", "neo4j"),
    ("database-design", "elasticsearch"),
    ("caching", "redis"),
    ("database-design", "caching"),

    # --- Infrastructure ----------------------------------------------------------------
    ("linux", "bash"),
    ("linux", "docker"),
    ("linux", "nginx"),
    ("networking", "nginx"),
    ("docker", "kubernetes"),
    ("networking", "kubernetes"),
    ("git", "ci-cd"),
    ("git", "github"),
    ("git", "gitlab"),
    ("github", "github-actions"),
    ("ci-cd", "github-actions"),
    ("ci-cd", "jenkins"),
    ("linux", "aws"),
    ("linux", "gcp"),
    ("linux", "azure"),
    ("aws", "serverless"),
    ("aws", "terraform"),
    ("linux", "ansible"),
    ("docker", "terraform"),

    # --- Messaging & architecture ------------------------------------------------------
    ("message-queues", "kafka"),
    ("message-queues", "rabbitmq"),
    ("message-queues", "celery"),
    ("concurrency", "message-queues"),
    ("rest-api", "microservices"),
    ("docker", "microservices"),
    ("microservices", "system-design"),
    ("caching", "system-design"),
    ("database-design", "system-design"),
    ("networking", "system-design"),
    ("javascript", "websockets"),
    ("networking", "websockets"),

    # --- Data & ML --------------------------------------------------------------------
    ("statistics", "machine-learning"),
    ("numpy", "machine-learning"),
    ("pandas", "machine-learning"),
    ("machine-learning", "scikit-learn"),
    ("machine-learning", "deep-learning"),
    ("deep-learning", "pytorch"),
    ("deep-learning", "tensorflow"),
    ("deep-learning", "computer-vision"),
    ("deep-learning", "nlp"),
    ("machine-learning", "embeddings"),
    ("pandas", "data-visualization"),
    ("statistics", "data-visualization"),
    ("python", "spark"),
    ("sql", "spark"),
    ("statistics", "r"),

    # --- Engineering practice ---------------------------------------------------------
    ("testing", "pytest"),
    ("testing", "jest"),
    ("testing", "playwright"),
    ("oop", "testing"),
    ("git", "code-review"),
    ("git", "agile"),
    ("rest-api", "authentication"),
    ("authentication", "security"),
    ("networking", "security"),
    ("ci-cd", "observability"),
    ("observability", "grafana"),
    ("observability", "prometheus"),
    ("observability", "sentry"),
    ("linux", "performance"),
    ("caching", "performance"),
    ("rest-api", "postman"),
    ("agile", "jira"),
    ("functional-programming", "scala"),
    ("javascript", "functional-programming"),
    ("java", "kotlin"),
    ("swift", "react-native"),
)
# fmt: on


class GraphValidationError(Exception):
    """The seed edges do not describe a usable learning graph."""


def validate_edges(edges: tuple[tuple[str, str], ...] = SEED_EDGES) -> None:
    """Reject edges that would make the graph unusable.

    Called by the seed migration, so a bad edge fails deployment loudly rather than producing
    silently wrong learning paths — which nobody would notice, because a wrong-but-plausible
    ordering looks exactly like a right one.
    """
    known = {skill.slug for skill in SEED_SKILLS}

    unknown = {slug for edge in edges for slug in edge if slug not in known}
    if unknown:
        raise GraphValidationError(f"Edges reference unknown skills: {sorted(unknown)}")

    self_loops = [edge for edge in edges if edge[0] == edge[1]]
    if self_loops:
        raise GraphValidationError(f"Skills cannot be their own prerequisite: {self_loops}")

    duplicates = [edge for edge in set(edges) if edges.count(edge) > 1]
    if duplicates:
        raise GraphValidationError(f"Duplicate edges: {sorted(duplicates)}")

    # Cycle detection without importing networkx — this runs inside a migration, and a
    # migration should not depend on the application's runtime libraries any more than it must.
    # Iterative depth-first search with a three-colour marking: white unvisited, grey on the
    # current stack, black finished. Meeting a grey node means an edge back into the path we
    # are currently walking, which is precisely a cycle.
    adjacency: dict[str, list[str]] = {}
    for prerequisite, skill in edges:
        adjacency.setdefault(prerequisite, []).append(skill)

    white, grey, black = 0, 1, 2
    colour = dict.fromkeys(known, white)

    for start in sorted(known):
        if colour[start] != white:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = [start]
        colour[start] = grey
        while stack:
            node, index = stack.pop()
            children = adjacency.get(node, [])
            if index < len(children):
                stack.append((node, index + 1))
                child = children[index]
                if colour[child] == grey:
                    cycle = [*path[path.index(child) :], child]
                    raise GraphValidationError(f"Cycle detected: {' -> '.join(cycle)}")
                if colour[child] == white:
                    colour[child] = grey
                    path.append(child)
                    stack.append((child, 0))
            else:
                colour[node] = black
                if path and path[-1] == node:
                    path.pop()
