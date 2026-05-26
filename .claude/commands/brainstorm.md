---
description: Refine a rough idea into an approved design document at docs/design.md
argument-hint: [optional rough idea]
---

Dispatch the `brainstorm` subagent via the Task tool. Pass the user's rough idea as starting context: $ARGUMENTS

The brainstorm agent will:
- Ask clarifying questions about goal, constraints, users, success criteria
- Present alternatives with trade-offs at each decision point
- Build the design section-by-section, validating each before moving on
- Write the final approved design to `docs/design.md`

Wait for brainstorm to complete. Surface its final report to the user.
