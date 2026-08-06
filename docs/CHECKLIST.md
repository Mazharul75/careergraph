# Engineering requirements checklist

The standards this project holds itself to. Updated at the end of every phase.

**Legend:** ✅ done · 🟡 partially done · ⬜ not started

_Last updated: end of Phase 0_

| # | Requirement | Status | Where it lives / when |
|---|---|---|---|
| 1 | System architecture documented (diagram + written rationale) | ✅ | [docs/architecture.md](architecture.md), Mermaid diagrams in README |
| 2 | Layered structure (routes → services → repositories), no logic in handlers | 🟡 | Structure scaffolded and documented; enforced in code from Phase 1 |
| 3 | A deliberate design pattern beyond MVC, explained not just used | 🟡 | Repository pattern + DI chosen and justified in architecture.md; implemented Phase 1 |
| 4 | Scalable backend (stateless API, async workers) | 🟡 | Designed and justified in [ADR-0002](adr/0002-technology-stack-selection.md); built Phases 1–2 |
| 5 | Relational DB design (normalized schema, ERD, Alembic migrations) | ⬜ | Phase 1 |
| 6 | Authentication + authorization (JWT, roles) | ⬜ | Phase 1 |
| 7 | REST API with OpenAPI/Swagger docs | ⬜ | Phase 1 (free via FastAPI) |
| 8 | Real git workflow: feature branches, PRs, conventional commits | 🟡 | Defined in [ADR-0004](adr/0004-trunk-based-branching-with-pull-requests.md) + CONTRIBUTING.md; proven by the history from Phase 0 onward |
| 9 | Automated tests written alongside each feature | ⬜ | Phase 1 |
| 10 | CI pipeline: lint + test on every push | ⬜ | Phase 1 |
| 11 | CD pipeline: auto-deploy on merge to `main` | ⬜ | Phase 1 (initial), hardened Phase 6 |
| 12 | A real, working deployment with a public link | ⬜ | Phase 1 (skeleton live), production-ready Phase 6 |
| 13 | Security basics: input validation, rate limiting, env-var secrets, dep scanning | 🟡 | `.gitignore` + secrets policy in place; the rest in Phase 5 |
| 14 | Monitoring: structured logs, error tracking, health checks | ⬜ | Phase 6 |
| 15 | Docs: README with diagram, setup instructions, ADR log | 🟡 | README, PRD, architecture, 4 ADRs written; setup instructions pending Phase 1 |
| 16 | A UI that looks like a product, not a template | ⬜ | Phase 4 |

## Phase 0 summary

**Fully done:** 1
**Started:** 2, 3, 4, 8, 13, 15
**Not started:** 5, 6, 7, 9, 10, 11, 12, 14, 16

Nothing is fully checked off except architecture documentation, which is correct — Phase 0
deliberately ships no feature code. The 🟡 items are cases where the decision is made and written
down but the code doesn't exist yet.
