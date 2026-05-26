---
description: Verify tests, choose disposition (merge/PR/keep/discard), and clean up the worktree
argument-hint: (none)
---

Dispatch the `pr-manager` subagent via the Task tool.

It will:
1. Run the full test suite — halt if anything fails
2. Show the branch state: current branch, commits ahead of main, one-line commit summaries, files changed
3. Present disposition options: **merge**, **PR**, **keep**, **discard**
4. Execute the chosen option (with explicit second confirmation on `discard`)
5. Clean up the worktree (unless `keep` was chosen)

Safety constraints enforced by pr-manager:
- Never merge if tests fail
- Never force-push
- Never skip hooks
- Always re-confirm before `discard`

Additional user context: $ARGUMENTS
