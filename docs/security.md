# Security posture

What protects this system, what deliberately does not, and where the honest edges are.
Requirement 13 asks for "security basics"; this document is the evidence, with pointers to
the code so every claim is checkable.

## Threat model, briefly

CareerGraph stores two things worth stealing: **credentials** (email + password hash) and
**resume text**. The realistic attackers are opportunistic: credential-stuffing bots,
password brute-forcers, and drive-by scanners hitting every public API they can find. This
is not a system that needs to resist a targeted nation-state — and pretending otherwise
would spend effort where no threat exists.

## Controls in place

### Authentication

| Control | Where | Why it matters |
|---|---|---|
| Argon2id password hashing | `core/security.py` | Memory-hard: GPU cracking rigs lose their advantage. Winner of the Password Hashing Competition; ~50 ms per verification is deliberate cost. |
| JWT access tokens, 15-minute lifetime | `core/config.py` | A JWT cannot be revoked, so its lifetime *is* the exposure window for a stolen one. |
| Opaque rotating refresh tokens, reuse detection | `services/auth.py`, ADR-0007 | Each refresh token works exactly once. Reuse of a spent token means theft — the whole family is revoked, ending both the attacker's and the victim's sessions. |
| Weak-secret guard at boot | `core/config.py` | The app refuses to start in staging/production with the published dev JWT key or any key under 32 bytes. A misconfigured deploy crashes visibly instead of serving forgeable tokens. |
| Uniform 401s | `api/deps.py`, `api/errors.py` | Wrong password, unknown account, expired token, and detected reuse are indistinguishable to the caller. Error detail is attacker information. |
| Deactivated-user check on every request | `api/deps.py` | The DB is consulted despite the token being self-describing — a disabled account loses access now, not at token expiry. |

### Rate limiting (Phase 5, ADR-0011)

Per-IP fixed windows in Redis on the three unauthenticated credential endpoints — the free
attack surface:

| Endpoint | Default limit | Rationale |
|---|---|---|
| `POST /auth/login` | 10 / 5 min | Humans mistype a handful of times; brute force needs millions. |
| `POST /auth/register` | 20 / hour | Account flooding is slow-burn abuse, not a burst. |
| `POST /auth/refresh` | 60 / min | Fires automatically from clients, so the ceiling is higher. |

Rejections are `429` with `Retry-After`. The limiter **fails open** when Redis is down —
consistent with `/health/ready` treating Redis as non-critical; failing closed would turn a
cache blip into a self-inflicted login outage. Limits are settings, tunable per environment
without a code change.

Known limits of the control, on purpose: per-IP keying does not stop a distributed attack
(it raises its price), and account-keyed lockout was rejected because it hands an attacker
a way to lock a victim out of their own account.

### Input validation

Every request body crosses a Pydantic schema with explicit bounds — no unbounded string
reaches a handler:

- Passwords: 12–128 chars, length over composition rules (NIST SP 800-63B). The *maximum*
  is a DoS guard: Argon2's cost scales with input, so an unbounded password field lets one
  request tie up a worker.
- Job descriptions: 30–50,000 chars, mirrored by a DB CHECK constraint.
- Uploads: 5 MB cap, extension **and magic-byte** checking — a `.pdf` whose bytes are not a
  PDF is rejected regardless of its Content-Type header; filenames are sanitised and
  truncated before storage.
- Path IDs are typed `uuid.UUID`; query params carry `max_length`; enums are `Literal`s
  that fail loudly on typos.
- SQL injection: no string-built SQL exists — every query goes through SQLAlchemy bound
  parameters. XSS: React escapes by default and no `dangerouslySetInnerHTML` is used.

### Secrets

- All secrets enter through environment variables, validated in one place
  (`core/config.py`); `SecretStr` keeps the JWT key out of logs, tracebacks and `repr()`.
- `.env` is git-ignored (with `.env.example` as the committed, placeholder-only template);
  production values live in Render's dashboard (`sync: false` in `render.yaml` means
  "prompt in dashboard, never store in git").
- A tracked-file scan for hardcoded credentials comes up clean; the only literal that looks
  like a secret is the dev placeholder, which production refuses to run with.
- The CI signing key is a throwaway literal, deliberately not a repository secret: nothing
  it signs leaves the runner, and real secrets in CI leak into fork build logs.

### Dependencies and platform

- **Dependabot** (`.github/dependabot.yml`) scans all four ecosystems weekly — uv, npm,
  GitHub Actions, and Docker base images — with minor/patch updates grouped to keep the
  signal readable. Its PRs pass through the same required CI as everyone else's.
- CORS is an explicit origin allowlist, never `*`.
- Swagger/OpenAPI endpoints are disabled in production.
- The container runs as a non-root user; workflows run with `permissions: contents: read`.

## Accepted risks — known, bounded, documented

| Risk | Why accepted | Bound |
|---|---|---|
| Registration reveals whether an email is taken (409) | The fix requires email delivery, which is out of scope (ADR-0007) | Rate limiting slows enumeration to a crawl |
| Refresh token readable by JS on the client | Cross-domain Vercel↔Render rules out cookies (ADR-0007) | 15-min access tokens + rotation + reuse detection |
| Fixed-window boundary burst (≤2× limit) | Doubling 10 Argon2-priced guesses is not a threat | ADR-0011 |
| Distributed (multi-IP) brute force not stopped | Per-IP is the strongest keying available without CAPTCHAs or lockout | Argon2 cost per guess still applies |
| No account lockout | Lockout is a denial-of-service gift to attackers | Rate limit + hashing cost |
| Jobs list is unpaginated | Authenticated-only; data volume is bounded at this scale | Revisit if listings become public/large |

**Why this matters in an interview:** every row here is a decision, not an omission. The
difference between "we don't have X" and "we considered X, and here is why not" is the
difference between a gap and an engineering trade-off.
