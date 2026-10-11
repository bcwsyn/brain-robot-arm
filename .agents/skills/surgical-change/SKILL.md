---
name: surgical-change
description: Use when implementing or reviewing a scoped fix in existing code, configuration, launch files, or tests; trace the behavior owner and make the smallest complete, verifiable change.
---

# Surgical changes in an existing system

This workflow supports the requested work; it is not a reason to delay it with unnecessary design ceremony. Repository-level instructions and the user's stated goal remain authoritative.

1. Locate the behavior owner and trace its callers, inputs, outputs, configuration, tests, and deployed copy. Separate verified facts from assumptions.
2. Define the requested behavior change, invariants that must remain unchanged, and the smallest test or runtime observation that verifies it.
3. Inspect the worktree first. Preserve unrelated user changes; do not reset, overwrite, stage, or commit them. Keep every edit tied to the requested fix.
4. Change the narrowest owning component. Avoid adjacent refactors, speculative abstractions, new dependencies, broad formatting, or weakening safety checks and tests.
5. Run the smallest relevant checks first, then only integration/runtime checks needed for the stated success criterion. Report build, unit-test, runtime, and hardware success as separate claims.
6. Inspect the final diff for scope and unintended changes. Follow repository progress/commit rules; stage only this task's files and hunks.
7. Continue already authorized, reversible work without repeated confirmation requests. Stop for a genuine missing decision, permission boundary, or safety condition not authorized by the repository/user; record the concrete blocker and next action.

## Source

Informed by the surgical-change implementer in [claude-code-skills](https://github.com/levnikolaevich/claude-code-skills/tree/main/plugins/implementation-suite/skills/ln-41-surgical-change-implementer), shortened and adapted to this repository's handoff rules. Not a verbatim copy.
