# Agent instructions

This project's agent instructions live in **[`CLAUDE.md`](CLAUDE.md)** (loaded automatically by
Claude Code) and **[`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)** (the live state).

This file is a pointer rather than a copy, deliberately: two sets of instructions drift apart,
and the moment they disagree neither can be trusted.

## Start here, in this order

1. **[`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)** — what is built, what is next, and the
   accumulated gotchas. §5 is the most valuable section in the repository.
2. **[`CLAUDE.md`](CLAUDE.md)** — how to work with this person, and the hard constraints.
3. **[`docs/adr/README.md`](docs/adr/README.md)** — 10 architecture decisions. Do not contradict
   one without reading it first.

## The three rules most easily broken

1. **Never touch the GitHub remote.** No `gh`, no `git push`, no `git pull`. Hand over exact
   commands instead. Local git reads are fine.
2. **He runs `cmd.exe`.** No `cd /d/PProject &&` prefixes in commands you give him.
3. **`git status --short` must be empty before he pushes.** Three CI failures came from an
   incomplete `git add`.

## Before you finish a phase

Update `docs/PROJECT_STATE.md` — status, new files, new ADRs, new gotchas — *then* write the
wrap-up. An un-updated state file means the next session starts blind.
