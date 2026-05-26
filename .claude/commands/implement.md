---
description: Set up a fresh branch and execute the plan at docs/plan.md task-by-task
argument-hint: (none)
---

Two-step dispatch. Order matters — do not skip or reorder.

**Step 1: Dispatch `git-master` via the Task tool.**

It will:
- Verify a clean working tree (halt if dirty)
- Create a new branch derived from the current goal in `docs/plan.md`
- Run project setup (install deps for the detected project type)
- Verify a clean test baseline (halt if any tests fail)

Wait for git-master to confirm success. If it halts for any reason, surface the issue to the user and **stop** — do not proceed to Step 2.

**Step 2: Dispatch `lead-developer` via the Task tool.**

It will:
- Read `docs/plan.md` and find the first unchecked task
- For each task, spawn a fresh `tdd-dev` to implement using RED-GREEN-REFACTOR
- Run two-stage review (`code-reviewer`): spec compliance, then code quality
- Check off completed tasks in `docs/plan.md`
- Pause after each task and ask the user `continue?`

Additional user context: $ARGUMENTS
