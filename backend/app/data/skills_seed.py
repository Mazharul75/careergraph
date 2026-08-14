"""The curated skill vocabulary.

Scoped deliberately to software engineering rather than spread thinly across every industry.
A shallow graph over all careers would produce vague advice everywhere; a dense one over a
single domain produces advice a student can act on. See the PRD's risk table.

`difficulty` (1-5) is unused until Phase 3, where it becomes the edge weight for shortest-path
search. Seeding it now means the graph phase starts with data rather than a spreadsheet.

`exact_case=True` marks skills whose names are also ordinary English words. Matched
case-insensitively, `Go`/`R`/`C` fire on "go to", "or", "a c library".

Aliases are the load-bearing part. Real resumes say "Postgres", "k8s", "JS", "ML" — a
vocabulary of canonical names alone would miss most real mentions.
"""

from __future__ import annotations

from typing import NamedTuple


class SeedSkill(NamedTuple):
    slug: str
    canonical_name: str
    category: str
    difficulty: int
    exact_case: bool
    aliases: tuple[str, ...]


# fmt: off
SEED_SKILLS: tuple[SeedSkill, ...] = (
    # --- Languages ---------------------------------------------------------------------
    SeedSkill("python", "Python", "language", 2, False, ("python3", "py")),
    SeedSkill("javascript", "JavaScript", "language", 2, False, ("js", "ecmascript")),
    SeedSkill("typescript", "TypeScript", "language", 3, False, ("ts",)),
    SeedSkill("java", "Java", "language", 3, False, ()),
    SeedSkill("c-sharp", "C#", "language", 3, False, ("csharp", "c sharp")),
    SeedSkill("cpp", "C++", "language", 4, False, ("cplusplus", "c plus plus")),
    SeedSkill("c", "C", "language", 4, True, ()),
    SeedSkill("go", "Go", "language", 3, True, ("golang",)),
    SeedSkill("rust", "Rust", "language", 4, True, ()),
    SeedSkill("ruby", "Ruby", "language", 2, False, ()),
    SeedSkill("php", "PHP", "language", 2, False, ()),
    SeedSkill("swift", "Swift", "language", 3, True, ()),
    SeedSkill("kotlin", "Kotlin", "language", 3, False, ()),
    SeedSkill("scala", "Scala", "language", 4, False, ()),
    SeedSkill("r", "R", "language", 3, True, ()),
    SeedSkill("sql", "SQL", "language", 2, False, ()),
    SeedSkill("bash", "Bash", "language", 2, False, ("shell scripting", "shell script")),
    SeedSkill("html", "HTML", "language", 1, False, ("html5",)),
    SeedSkill("css", "CSS", "language", 2, False, ("css3",)),

    # --- Backend frameworks -------------------------------------------------------------
    SeedSkill("fastapi", "FastAPI", "framework", 3, False, ()),
    SeedSkill("django", "Django", "framework", 3, False, ("django rest framework", "drf")),
    SeedSkill("flask", "Flask", "framework", 2, False, ()),
    SeedSkill("express", "Express.js", "framework", 2, False, ("express", "expressjs")),
    SeedSkill("nestjs", "NestJS", "framework", 3, False, ("nest.js",)),
    SeedSkill("spring-boot", "Spring Boot", "framework", 4, False, ("spring",)),
    SeedSkill("dotnet", "ASP.NET", "framework", 3, False, ("asp.net core", ".net", "dotnet")),
    SeedSkill("rails", "Ruby on Rails", "framework", 3, False, ("rails",)),
    SeedSkill("laravel", "Laravel", "framework", 3, False, ()),
    SeedSkill("celery", "Celery", "framework", 3, False, ()),

    # --- Frontend -----------------------------------------------------------------------
    SeedSkill("react", "React", "framework", 3, False, ("react.js", "reactjs")),
    SeedSkill("react-native", "React Native", "framework", 4, False, ()),
    SeedSkill("nextjs", "Next.js", "framework", 3, False, ("nextjs",)),
    SeedSkill("vue", "Vue.js", "framework", 3, False, ("vue", "vuejs")),
    SeedSkill("angular", "Angular", "framework", 4, False, ()),
    SeedSkill("svelte", "Svelte", "framework", 3, False, ("sveltekit",)),
    SeedSkill("tailwind", "Tailwind CSS", "framework", 2, False, ("tailwindcss", "tailwind")),
    SeedSkill("redux", "Redux", "framework", 3, False, ()),

    # --- Databases ----------------------------------------------------------------------
    SeedSkill("postgresql", "PostgreSQL", "database", 3, False, ("postgres", "psql")),
    SeedSkill("mysql", "MySQL", "database", 2, False, ()),
    SeedSkill("sqlite", "SQLite", "database", 1, False, ()),
    SeedSkill("mongodb", "MongoDB", "database", 2, False, ("mongo",)),
    SeedSkill("redis", "Redis", "database", 2, False, ()),
    SeedSkill("elasticsearch", "Elasticsearch", "database", 4, False, ("elastic search",)),
    SeedSkill("cassandra", "Cassandra", "database", 4, False, ()),
    SeedSkill("neo4j", "Neo4j", "database", 4, False, ()),
    SeedSkill("pgvector", "pgvector", "database", 3, False, ()),
    SeedSkill("sqlalchemy", "SQLAlchemy", "framework", 3, False, ()),
    SeedSkill("prisma", "Prisma", "framework", 2, False, ()),
    SeedSkill("database-design", "Database Design", "concept", 3, False, ("schema design", "normalization", "erd")),

    # --- Infrastructure & DevOps ----------------------------------------------------------
    SeedSkill("docker", "Docker", "infrastructure", 3, False, ("containerization", "containers")),
    SeedSkill("kubernetes", "Kubernetes", "infrastructure", 5, False, ("k8s",)),
    SeedSkill("linux", "Linux", "infrastructure", 3, False, ("unix",)),
    SeedSkill("nginx", "Nginx", "infrastructure", 3, False, ()),
    SeedSkill("terraform", "Terraform", "infrastructure", 4, False, ()),
    SeedSkill("ansible", "Ansible", "infrastructure", 3, False, ()),
    SeedSkill("aws", "AWS", "infrastructure", 4, False, ("amazon web services",)),
    SeedSkill("gcp", "Google Cloud", "infrastructure", 4, False, ("gcp", "google cloud platform")),
    SeedSkill("azure", "Azure", "infrastructure", 4, False, ("microsoft azure",)),
    SeedSkill("ci-cd", "CI/CD", "concept", 3, False, ("continuous integration", "continuous deployment", "cicd")),
    SeedSkill("github-actions", "GitHub Actions", "tool", 2, False, ()),
    SeedSkill("jenkins", "Jenkins", "tool", 3, False, ()),
    SeedSkill("serverless", "Serverless", "concept", 3, False, ("lambda", "aws lambda")),
    SeedSkill("networking", "Networking", "concept", 3, False, ("tcp/ip", "dns")),

    # --- Data & ML ------------------------------------------------------------------------
    SeedSkill("machine-learning", "Machine Learning", "data_ml", 4, False, ("ml",)),
    SeedSkill("deep-learning", "Deep Learning", "data_ml", 5, False, ("neural networks",)),
    SeedSkill("nlp", "Natural Language Processing", "data_ml", 4, False, ("nlp",)),
    SeedSkill("computer-vision", "Computer Vision", "data_ml", 5, False, ("cv",)),
    SeedSkill("pandas", "pandas", "data_ml", 2, False, ()),
    SeedSkill("numpy", "NumPy", "data_ml", 2, False, ()),
    SeedSkill("scikit-learn", "scikit-learn", "data_ml", 3, False, ("sklearn", "scikit learn")),
    SeedSkill("pytorch", "PyTorch", "data_ml", 4, False, ("torch",)),
    SeedSkill("tensorflow", "TensorFlow", "data_ml", 4, False, ("keras",)),
    SeedSkill("spark", "Apache Spark", "data_ml", 4, False, ("pyspark", "spark")),
    SeedSkill("statistics", "Statistics", "concept", 3, False, ("statistical analysis",)),
    SeedSkill("data-visualization", "Data Visualization", "concept", 2, False, ("matplotlib", "seaborn")),
    SeedSkill("embeddings", "Vector Embeddings", "data_ml", 4, False, ("embeddings", "semantic search")),

    # --- Tools -----------------------------------------------------------------------------
    SeedSkill("git", "Git", "tool", 2, False, ("version control",)),
    SeedSkill("github", "GitHub", "tool", 1, False, ()),
    SeedSkill("gitlab", "GitLab", "tool", 2, False, ()),
    SeedSkill("jira", "Jira", "tool", 1, False, ()),
    SeedSkill("figma", "Figma", "tool", 2, False, ()),
    SeedSkill("postman", "Postman", "tool", 1, False, ()),
    SeedSkill("grafana", "Grafana", "tool", 3, False, ()),
    SeedSkill("prometheus", "Prometheus", "tool", 3, False, ()),
    SeedSkill("sentry", "Sentry", "tool", 2, False, ()),
    SeedSkill("kafka", "Apache Kafka", "infrastructure", 4, False, ("kafka",)),
    SeedSkill("rabbitmq", "RabbitMQ", "infrastructure", 3, False, ()),
    SeedSkill("graphql", "GraphQL", "concept", 3, False, ()),
    SeedSkill("websockets", "WebSockets", "concept", 3, False, ("socket.io", "websocket")),

    # --- Concepts ----------------------------------------------------------------------------
    SeedSkill("rest-api", "REST API Design", "concept", 3, False, ("rest", "restful", "rest api")),
    SeedSkill("microservices", "Microservices", "concept", 4, False, ("microservice architecture",)),
    SeedSkill("system-design", "System Design", "concept", 5, False, ("distributed systems",)),
    SeedSkill("oop", "Object-Oriented Programming", "concept", 2, False, ("oop", "object oriented")),
    SeedSkill("functional-programming", "Functional Programming", "concept", 4, False, ("fp",)),
    SeedSkill("data-structures", "Data Structures", "concept", 3, False, ()),
    SeedSkill("algorithms", "Algorithms", "concept", 3, False, ("algorithm design",)),
    SeedSkill("graph-theory", "Graph Theory", "concept", 4, False, ("graph algorithms",)),
    SeedSkill("testing", "Automated Testing", "concept", 3, False, ("unit testing", "unit tests", "tdd")),
    SeedSkill("pytest", "pytest", "tool", 2, False, ()),
    SeedSkill("jest", "Jest", "tool", 2, False, ()),
    SeedSkill("playwright", "Playwright", "tool", 3, False, ()),
    SeedSkill("agile", "Agile", "concept", 2, False, ("scrum", "kanban")),
    SeedSkill("code-review", "Code Review", "concept", 2, False, ()),
    SeedSkill("authentication", "Authentication", "concept", 3, False, ("jwt", "oauth", "oauth2")),
    SeedSkill("security", "Application Security", "concept", 4, False, ("appsec", "owasp")),
    SeedSkill("caching", "Caching", "concept", 3, False, ()),
    SeedSkill("message-queues", "Message Queues", "concept", 3, False, ("message queue", "task queue")),
    SeedSkill("observability", "Observability", "concept", 4, False, ("monitoring", "structured logging")),
    SeedSkill("performance", "Performance Optimization", "concept", 4, False, ("profiling", "load testing")),
    SeedSkill("accessibility", "Web Accessibility", "concept", 3, False, ("a11y", "wcag")),
    SeedSkill("responsive-design", "Responsive Design", "concept", 2, False, ("mobile first",)),
    SeedSkill("api-documentation", "API Documentation", "concept", 2, False, ("openapi", "swagger")),
    SeedSkill("concurrency", "Concurrency", "concept", 4, False, ("multithreading", "async programming", "asyncio")),
)
# fmt: on


def alias_conflicts() -> dict[str, list[str]]:
    """Terms claimed by more than one skill.

    A term mapping to two skills makes extraction nondeterministic — "js" resolving to both
    JavaScript and Java would mean the result depends on dictionary ordering. The database has
    a unique constraint on `skill_aliases.term`, so a conflict fails the seed migration; this
    helper exists so a test can report *which* terms clash instead of just "unique violation".
    """
    seen: dict[str, list[str]] = {}
    for skill in SEED_SKILLS:
        for term in (skill.canonical_name, *skill.aliases):
            seen.setdefault(term.lower(), []).append(skill.slug)
    return {term: owners for term, owners in seen.items() if len(owners) > 1}
