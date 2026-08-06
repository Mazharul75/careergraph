# CareerGraph — Product Requirements

**Author:** MD Mazharul Islam Nabil
**Status:** Approved for build
**Last updated:** Phase 0

---

## 1. Problem

Students and early-career developers can read a job posting and still not know what to *do* about it.

Three things go wrong:

1. **The gap is invisible.** A posting lists twenty requirements. Which ones does the candidate
   already satisfy under a different name? "Built REST services in Python" and "experience with
   FastAPI" are the same competency; keyword matching says they are unrelated.
2. **The gap is unordered.** Even when someone knows they're missing *Kubernetes*, *Docker*, and
   *Linux fundamentals*, nothing tells them these have a natural learning order. Starting with
   Kubernetes wastes weeks.
3. **The comparison doesn't scale.** Doing this by hand against 30 postings takes an evening and
   produces inconsistent judgements.

Existing tools are either resume keyword-scanners (shallow, gameable) or generic course
recommenders (not grounded in a specific target job).

## 2. Users

| User | Role in system | What they need |
|---|---|---|
| **Job seeker** (primary) | `job_seeker` | Upload a resume once, compare it against many jobs, get an ordered learning path for a chosen target |
| **Recruiter** (secondary) | `recruiter` | Post a job description, see ranked candidate matches with the reasoning visible |

The two roles exist so authorization is a real feature with a real test surface, not a token
`is_admin` flag. Recruiter functionality is deliberately narrow — the job seeker is the focus.

## 3. Goals

- **G1** — Given a resume, extract a structured skill profile automatically, with no manual tagging.
- **G2** — Given a job description, produce a match score that reflects *meaning*, not shared words.
- **G3** — Given a target job, return an **ordered** sequence of skills to learn, where each skill's
  prerequisites appear before it.
- **G4** — Never block an HTTP request on slow work. Resume parsing and embedding generation happen
  off the request path.
- **G5** — Be genuinely production-shaped: authenticated, tested, monitored, CI/CD-deployed, and
  publicly reachable at a URL.

## 4. Non-goals

Explicitly **out of scope**, so scope creep is a decision rather than an accident:

- Scraping job boards. Job descriptions are pasted or entered via API.
- Training a custom ML model. We use pre-trained sentence embeddings.
- Course/content recommendations with affiliate links. We recommend *skills*, not vendors.
- Messaging, applications, or an ATS. Not a job board.
- Mobile apps. Responsive web only.
- Multi-tenancy / organizations. Individual accounts only.

## 5. Core user stories

**Job seeker**

- As a job seeker, I can register and log in, so my data is private to me.
- As a job seeker, I can upload a resume and get an immediate acknowledgement, so the UI never hangs.
- As a job seeker, I can poll or be shown the parse status, so I know when my profile is ready.
- As a job seeker, I can see my extracted skills and correct them, because NLP extraction is not
  perfect and a wrong profile poisons every downstream result.
- As a job seeker, I can add a job description and see a match score with the matched and missing
  skills broken out, so the score is explainable rather than a magic number.
- As a job seeker, I can pick a target job and receive an ordered learning path, so I know what to
  study first.

**Recruiter**

- As a recruiter, I can post a job description.
- As a recruiter, I can see candidates ranked by match score for my posting.
- As a recruiter, I cannot access another user's resume or another recruiter's postings.

**Cross-cutting**

- As any user, my session survives a page refresh without re-login, via refresh-token rotation.
- As an operator, I can hit `/health` and know whether the API, database, and queue are alive.

## 6. Success criteria

The project is done when all of these are demonstrably true:

| # | Criterion | How it's verified |
|---|---|---|
| S1 | A stranger can visit a public URL, register, and complete the full flow | Live demo link |
| S2 | Resume upload returns in < 500 ms regardless of file size | Parsing is a Celery task; timing asserted in tests |
| S3 | Match scores are semantic, not lexical | Test case: zero keyword overlap, high score |
| S4 | Learning paths are topologically valid | Property test: no skill precedes its prerequisite |
| S5 | Every push runs lint + tests; every merge to `main` deploys | Green GitHub Actions history |
| S6 | Meaningful test coverage on services and graph logic | Coverage reported in CI |
| S7 | No secret has ever been committed | Secrets audit in Phase 5 |
| S8 | An unauthenticated request to a protected route is rejected | Integration test |

## 7. Key product decisions

**Skills are a graph, not a list.** This is the product's spine. Modelling prerequisites as directed
edges is what makes an *ordered* plan possible; a flat skill list can only ever produce a set
difference. See [ADR 0002](adr/0002-technology-stack-selection.md) for why NetworkX rather than a
graph database.

**Scores must be explainable.** Every match score ships with the skills that matched and the skills
that are missing. An unexplained 73% is not actionable and users won't trust it.

**Extraction is correctable.** NLP will mis-parse resumes. Letting users fix their own profile is
cheaper and more honest than pretending the pipeline is perfect.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Skill-graph seed data is the hard, unglamorous part | Start with a curated ~150-skill graph in one domain (software engineering) rather than a shallow graph across all industries |
| Resume formats are wildly inconsistent | Support PDF and DOCX only; fail loudly with a clear error rather than silently extracting garbage |
| Free-tier hosting cold-starts | `/health` endpoint plus an honest note in the README; acceptable for a portfolio deployment |
| Embedding model size vs. free-tier memory | Use a small sentence-transformer model; measure memory in Phase 2 before committing |
| Scope creep from "wouldn't it be cool if…" | The non-goals list above is binding; changes to it require an ADR |
