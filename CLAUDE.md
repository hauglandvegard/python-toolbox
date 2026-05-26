# CLAUDE.md

Project context for Claude Code. Drop this file and `.claude/` into a new project root together.

## Project

`python-toolbox` — personal Python utility library for scraping, string manipulation, IO, datetime, and other general-purpose helpers. Intended to be hosted on GitHub and installed as a package into other projects via `pip install git+https://github.com/hauglandvegard/python-toolbox.git`. Stack: Python 3.14+, `src/` layout, `pyproject.toml` (hatchling backend).

Architecture reference: `/Users/vegard/Vault/vault/conversations/2026-05/26-01 Python Toolbox Project/architecture_guide.md`.

## Workflow

This project uses a 4-phase agent workflow driven by slash commands. Each phase has a single entry point; do not skip phases or run them out of order.

```
/brainstorm  →  docs/design.md  →  docs/plan.md
     ↓
/implement   →  branch + commits per task
     ↓
/merge       →  disposition (merge/PR/keep/discard)
```

### `/brainstorm [rough idea]`
Two-step: `brainstorm` agent drives a section-by-section design dialogue → `docs/design.md`. Then `planner` agent decomposes the design into goals and commit-sized tasks → `docs/plan.md` with checkboxes.

### `/implement`
Two-step: `git-master` sets up branch + verifies clean test baseline, then `lead-developer` drives `docs/plan.md` task-by-task. Each task gets a fresh `tdd-dev` (RED-GREEN-REFACTOR) and two-stage review by `code-reviewer`. Pauses after every task for `continue?`.

### `/merge`
Verifies tests, presents disposition options, cleans up the worktree.

## Agents

Located in `.claude/agents/`. Auto-discovered by Claude Code.

| Agent | Role | Model |
|---|---|---|
| `brainstorm` | Design dialogue → `docs/design.md` | opus |
| `planner` | `design.md` → `docs/plan.md` (goals + tasks) | opus |
| `git-master` | Branch setup, project install, clean baseline | sonnet |
| `lead-developer` | Orchestrates tasks, dispatches TDD devs, runs reviews | sonnet |
| `tdd-dev` | One task, strict RED-GREEN-REFACTOR, one commit | sonnet |
| `code-reviewer` | Two-stage review: spec compliance, then code quality | opus |
| `pr-manager` | Test + disposition + worktree cleanup | sonnet |

## Artifacts

| Path | Written by | Read by |
|---|---|---|
| `docs/design.md` | `brainstorm` | `planner` |
| `docs/plan.md` | `planner` | `lead-developer`, `tdd-dev` (task brief), `code-reviewer` |
| `logs/agents.log` | every agent | humans |

Log format: `<ISO-8601 time> <agent> <DEBUG|INFO|WARNING|ERROR|CRITICAL> <message>`

## Conventions

- **No internet access for subagents.** All language/framework knowledge comes from central `expert-*` agents in `~/.claude/agents/` (Docker, Go, Go-Wails, JS, HTMX, Python, FastAPI, Rust, TS, React, Svelte). If a question requires a language not covered, agents halt.
- **One task = one commit.** TDD devs never bundle.
- **Tests must pass before merge.** PR-manager enforces.
- **Plan is source of truth.** Lead developer does not invent tasks; if the plan is wrong, re-run `@planner`.

## Project-specific conventions

### Layout

- **`src/` layout.** Package code lives in `src/toolbox/`. Avoids accidental root-relative imports; tests run against the installed package.
- **Flat module hierarchy** under `toolbox/`. Each utility area is a top-level subpackage (`toolbox.scraper`, `toolbox.strings`, `toolbox.io`, `toolbox.dt`, `toolbox.cli`, `toolbox.paths`, `toolbox.async_utils`, `toolbox.validation`, `toolbox.system`, `toolbox.cache`, `toolbox.net`, `toolbox.db`, `toolbox.secrets`, `toolbox.encoding`, `toolbox.git`, `toolbox.inspect`, `toolbox.retry`, `toolbox.testing`, `toolbox.concurrency`, `toolbox.math`). Do **not** introduce grouped namespaces (`toolbox.web.*`, `toolbox.core.*`) — short import paths win at this scale.
- **Hoist public API** in each subpackage `__init__.py` (`from .core import scrape_links, ScraperClient`) so users can write `from toolbox.scraper import scrape_links`.

### Build / packaging

- **`pyproject.toml`** is the single source of build config. No `setup.py`.
- Installable from GitHub:
  ```
  python-toolbox @ git+https://github.com/hauglandvegard/python-toolbox.git
  ```

### Logging

- **Library code MUST NOT call `logging.basicConfig()`** or otherwise configure root logging.
- Every module gets its own logger:
  ```python
  import logging
  logger = logging.getLogger(__name__)
  ```
- Root `src/toolbox/__init__.py` attaches a `NullHandler` to suppress "no handler found" warnings:
  ```python
  import logging
  logging.getLogger(__name__).addHandler(logging.NullHandler())
  ```
- Pass structured fields via the stdlib `extra=` parameter (e.g. `logger.info("Starting scrape", extra={"url": url})`). This stays stdlib-only but is consumable by `structlog` via `structlog.stdlib.ExtraAdder()` in the host app.

### Commands

- **Target runtime:** Python 3.14+ (`requires-python = ">=3.14"`).
- **Install (dev):** `pip install -e ".[dev]"`
- **Test:** `pytest`
- **Lint:** `ruff check .`
- **Format:** `ruff format .`
- **Type check:** `mypy` (strict mode, configured in `pyproject.toml`)
- **Build:** `python -m build`

## Setup checklist for a fresh project

1. Drop this `CLAUDE.md` and the `.claude/` folder into the project root.
2. Fill in the **Project** and **Project-specific conventions** sections above.
3. Run `/brainstorm <your idea>` to start.
