# ADR-0004: Trunk-based branching with pull requests

- **Status:** Accepted
- **Date:** 2026-08-06
- **Phase:** 0

## Context

This is a solo project, so a branching model is not strictly necessary — commits could go straight to
`main`. But two of the project's stated goals depend on the git history itself:

1. Demonstrate a **real engineering workflow**, since prior projects have thin histories with no
   branches, no PRs, and no review trail.
2. Support **CD**, where merging to `main` triggers a deployment. That only works if `main` is
   always releasable, which requires a gate before code lands.

The history is part of the deliverable. It should read like a project that was built deliberately.

## Decision

**Trunk-based development with short-lived feature branches and pull requests.**

- `main` is the trunk. It is always deployable and is protected: no direct pushes; CI must be green
  before merge.
- Work happens on branches named `<type>/<short-description>`, e.g. `feat/jwt-refresh-rotation`.
  Types match the Conventional Commits types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`,
  `ci`, `perf`.
- Branches are **short-lived** — ideally under a day, always under a phase. Long branches produce
  painful merges and hide work from CI.
- Every change goes through a pull request, including solo work. The PR body states what changed and
  why, and links the ADR if one applies.
- Commit messages follow **Conventional Commits**: `type(scope): subject`.
- PRs are merged with **`--no-ff` merge commits**, preserving both the individual commits and the
  branch topology.

## Alternatives considered

- **Git Flow** (`develop` + `release/*` + `hotfix/*`). Designed for versioned software with
  scheduled releases and multiple supported versions. For a continuously deployed web app it adds
  long-lived branches and merge overhead with nothing to show for it.
- **Committing directly to `main`.** Fastest, and defensible for a solo project — but it makes branch
  protection meaningless, removes the CI gate before deploy, and produces exactly the flat history
  this project exists to avoid.
- **Squash-merge every PR.** Common in industry and it keeps `main` tidy — one commit per feature.
  Rejected here specifically because the granular commits *are* portfolio evidence: they show
  incremental, test-alongside development rather than a wall of finished code. Squashing would flatten
  that into a handful of large commits. The cost accepted is a busier `git log`, mitigated by
  `git log --first-parent`, which shows only the merge commits when a clean overview is wanted.
- **Rebase-merge.** Linear history without merge commits, but it loses the branch topology and
  rewrites commit SHAs after review — the reviewed commits are not the merged ones.

## Consequences

**Better**

- `main` stays deployable, which is a hard prerequisite for the CD pipeline in Phase 6.
- `git log --graph` shows genuine feature-branch topology.
- Every change has a PR with a written rationale — a searchable record beyond the diff.
- Conventional Commits make the history machine-readable, so a changelog can be generated later.

**Worse / accepted**

- Real ceremony for a solo developer: branch, push, open PR, wait for CI, merge. Roughly a minute per
  change plus CI time.
- Self-approving PRs is theatre in the literal sense — there is no second reviewer. The value is the
  CI gate and the written rationale, not the approval click.
- Merge commits make `git log` noisier than a squashed history.
- Discipline is required: the temptation to push a one-line fix straight to `main` will be constant,
  and branch protection is what makes that impossible rather than merely discouraged.
