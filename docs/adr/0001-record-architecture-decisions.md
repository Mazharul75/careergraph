# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-08-06
- **Phase:** 0

## Context

This project makes a large number of non-obvious choices — why `pgvector` and not a vector database,
why NetworkX and not Neo4j, why refresh-token rotation and not long-lived tokens. Those reasons are
vivid while making the choice and gone a month later.

Two audiences need them later:

1. **Me, maintaining this.** Without a record, a past decision looks arbitrary, gets "cleaned up",
   and the original constraint reappears as a bug.
2. **An interviewer.** "Why did you use X?" is the single most common follow-up to any portfolio
   project, and "it seemed fine" is a losing answer. A written ADR turns a vague memory into a
   defensible position.

Code comments don't solve this: they explain what a line does, not why an option was rejected before
any line was written.

## Decision

Every significant architectural decision gets an ADR in `docs/adr/`, in the format described in
[docs/adr/README.md](README.md), following Michael Nygard's ADR convention.

"Significant" means: it is expensive to reverse, it constrains later choices, or a reasonable
engineer would have chosen differently.

ADRs are written **at the time of the decision**, in the same pull request as the code that
implements it — not reconstructed at the end of the project.

## Alternatives considered

- **A single `DECISIONS.md` file.** Simpler, but it grows into an unreadable wall, and there's no
  natural way to mark one decision superseded without rewriting shared history.
- **GitHub issues or a wiki.** Decisions drift away from the code they govern and don't get reviewed
  in the PR that implements them.
- **Nothing; rely on commit messages.** Commit messages explain a change, not the option space that
  existed before it.

## Consequences

**Better:** Reasoning survives. Reviewing an ADR forces me to actually articulate the trade-off,
which sometimes changes the decision. The `docs/adr/` directory becomes concrete interview material.

**Worse:** Every meaningful decision carries a documentation cost, and there's a judgement call about
what clears the "significant" bar. Over-documenting trivia dilutes the log as badly as documenting
nothing.
