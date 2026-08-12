# ADR-0007: Opaque rotating refresh tokens with reuse detection

- **Status:** Accepted
- **Date:** 2026-08-11
- **Phase:** 1b

## Context

[ADR-0002](0002-technology-stack-selection.md) committed to JWT access tokens plus refresh
tokens, because a stateless API cannot look sessions up in shared memory. That left three
questions unanswered, all of which materially affect security:

1. What *is* a refresh token — a second JWT, or an opaque value?
2. How does it reach the client — response body, or httpOnly cookie?
3. What happens when one is stolen?

The third is the one that matters. A JWT cannot be revoked before it expires, so the entire
security of the scheme rests on keeping the access token short-lived and the refresh token
protected. A refresh token that is valid for thirty days and never changes is simply a password
with extra steps.

Deployment shape constrains the answer: the frontend runs on Vercel and the API on Render, on
unrelated domains.

## Decision

**Refresh tokens are opaque random strings, not JWTs.** 256 bits from `secrets.token_urlsafe`.
Only a SHA-256 hash is stored; the raw value is returned once and never again.

**They are single-use and rotate.** Every refresh revokes the presented token and issues a
successor, linked by `replaced_by_id`, sharing a `family_id` with everything descended from the
same login.

**Reuse of a spent token revokes the whole family.** A single-use token presented twice means a
copy exists somewhere it should not. The entire rotation chain is revoked, ending both the
attacker's session and the legitimate user's, forcing re-authentication.

**Both tokens are returned in the JSON response body.** The client stores the refresh token;
the access token is expected to be held in memory.

**Access tokens live 15 minutes; refresh tokens 30 days.**

## Alternatives considered

### Refresh tokens as JWTs

Common, and it removes a database read on the refresh path. Rejected because we need
server-side state regardless — revocation, rotation chains, and reuse detection all require a
row per token. Once that row exists, signing a JWT adds size and parsing cost while providing
nothing the row does not already provide. Worse, a self-validating refresh JWT tempts an
implementation into skipping the database read, which silently removes revocation entirely.

Storing only a hash is the second benefit: a leaked database dump contains no usable tokens. A
JWT stored verbatim would be immediately replayable.

### httpOnly cookie for the refresh token

Genuinely stronger against XSS: JavaScript cannot read the token at all, so a script injection
cannot exfiltrate it. This is the textbook answer and it was seriously considered.

Rejected for **this deployment**, on three grounds:

1. **Third-party cookie blocking.** A cookie set by `careergraph-api.onrender.com` and sent
   from a `careergraph.vercel.app` page is third-party. Safari blocks these by default and
   Chrome is retiring them. Choosing a mechanism that is more secure in theory and unreliable
   in practice is worse than choosing a simpler one and mitigating it honestly.
2. **CSRF.** `SameSite=None` is required for cross-site use, which reintroduces CSRF and the
   need for a token or double-submit scheme — more security-critical code, not less.
3. It would require a custom domain with API and frontend on sibling subdomains. Worth
   revisiting if that ever happens; this ADR would then be superseded.

The accepted mitigation for XSS exposure is the combination of a 15-minute access token, single
use rotation, and reuse detection: a stolen refresh token is usable at most until the real user
next refreshes, at which point the theft is detected and the session dies.

### Rotation without reuse detection

Simpler, and it does bound how long a stolen token stays useful. Rejected because it discards
most of the value: rotation makes theft *temporary*, while reuse detection makes it
*detectable*. The extra cost is one nullable column and one bulk UPDATE.

### Revoking only the replayed token

Gentler — nobody gets logged out unexpectedly. Rejected because it does not stop the attack. If
the thief holds a copy of the chain, rejecting one token just means they try the next. Family
revocation is the only response that actually ends the compromised session.

### Long-lived access tokens with no refresh at all

Rejected outright. A leaked token would be valid for its full lifetime with no remedy.

## Consequences

**Better**

- A stolen refresh token has a short useful life and its use is *detected*, not merely survived.
- A database leak yields no usable tokens, only hashes.
- The rotation chain is a forensic record: after an incident, `family_id` and `replaced_by_id`
  reconstruct exactly what was issued and when.
- Sessions are independent — a compromise on one device does not sign the user out of another.
- No cookie means no CSRF surface on the auth endpoints and no cross-site cookie fragility.

**Worse / accepted**

- **XSS on the frontend means refresh-token theft.** This is the real cost of not using an
  httpOnly cookie, and it is not hand-waved away — it is bounded by rotation and detection, not
  eliminated. Phase 4 must therefore treat output escaping and dependency provenance as
  security-critical, and Phase 5's review will cover it explicitly.
- **False positives log users out.** Two tabs refreshing simultaneously, or a network retry
  after a response is lost, can present the same token twice and trip detection. Accepted:
  erring toward "end the session" is the right default for a security control. A short grace
  window is the standard mitigation if this proves annoying in practice.
- **Every refresh costs a database round-trip.** Unavoidable given revocation is required, and
  the lookup is a single indexed read on `token_hash`.
- **`refresh_tokens` grows without bound.** Spent rows cannot be deleted eagerly, because
  detecting reuse depends on them still existing. A scheduled cleanup of rows past their expiry
  is needed — deferred to Phase 6 alongside the other operational work.
- Logout requires the refresh token in the request body rather than being inferable from a
  cookie.
