# AGENTS.md

Guidance for AI coding agents working in this repository.

## Architecture is the source of truth

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the core of every decision in this project. Read it before you plan or write anything.

- Every change must follow it. This covers code, configuration, dependencies and infrastructure. The document defines the stack, components, processing pipeline, data model, storage layout, permissions, API, deployment and roadmap.
- Stop and ask the user when:
  - a task conflicts with the architecture;
  - the architecture does not cover a decision the task needs;
  - you are unsure whether something counts as an architecture change.

  Do not improvise or work around the architecture silently.
- Follow the roadmap order in the architecture. Phase 2 (remote access) is postponed: do not implement it until the user explicitly says so.

## Changing the architecture

**Never edit `docs/ARCHITECTURE.md` without the user's explicit approval.**

1. Propose the change first. Say which section changes, what changes, why, and how it affects code that already exists.
2. Wait for an explicit "yes" from the user. Silence, or approval of something else, is not approval.
3. Only then edit `docs/ARCHITECTURE.md`. Make the edit before the code that depends on it, or in the same change.

These also count as architecture changes and need approval:

- replacing or adding a library or tool in the stack;
- adding or changing tables, columns or statuses;
- adding endpoints or WebSocket events;
- changing pipeline stages;
- changing the storage layout;
- changing the permission rules or deployment services.

An approval covers only the change that was approved. It does not carry over to later changes.

The document is written in Brazilian Portuguese; keep it that way.

## Git workflow

- Never commit directly to `main`. Work on a branch.
- Commit and push only when the user asks.
- After pushing, ask the user whether to merge straight into `main` or to open a pull request. Ask every time; a past answer does not carry over.
