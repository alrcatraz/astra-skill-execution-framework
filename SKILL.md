---
name: execution-framework
description: >
  Task classification and routing. Use this when starting any task — research,
  plan, modify, deploy, fix, analyse, investigate, close — to identify the
  correct work principles and supporting skills for this type of work.
category: devops
version: 2.0.0
---

# Execution Framework

A single entry point for any task. Load this skill, classify the task, then
follow the corresponding workflow checklist.

## Trigger Conditions

This skill is automatically loaded when starting almost any task:
- Research, plan, analyse, design, propose
- Modify, configure, fix, repair, debug
- Deploy, install, register, set up, publish
- Close, wrap up, summarise, clean up
- Investigate, diagnose, troubleshoot, audit

When in doubt, load this skill — it is designed to handle the widest possible
range of tasks. The overhead is reading one classification table and following
one checklist; the benefit is never skipping a necessary step.

## Auto-Check (Self-Evolution)

On load, run `scripts/sync-routing.py --diff` to verify the routing table is
current. The script:

1. **Timestamp cache check** — compares routing.yaml mtime vs registry.yaml mtime
   - If routing is newer → silently passes (zero overhead)
   - If registry is newer → full diff, reports gaps
2. **Gap report** — lists unregistered skills (in registry, not in routing)
   and orphans (in routing, not in registry)
3. **If gaps found** → present them to the user, ask approval, then
   run `scripts/sync-routing.py --apply` (interactive) or
   `--auto` (non-interactive, for cron)

This makes the routing table self-evolving: new skills automatically get
detected and suggested for addition.

> **Note for non-interactive environments (cron, headless):**
> Set up a cron job to run `sync-routing.py --cron-check` daily. When it
> exits with code 1 (gaps found), the output can be piped to a notification.
> Run `sync-routing.py --auto --apply` in cron to auto-add new skills.

## Classification Table

Read this table when the skill loads. Identify which row best matches your
task, then load the corresponding checklist skill and proceed.

The definitive source is `routing.yaml` (machine-readable). The table below is a
human-friendly reference — always prefer reading `routing.yaml` directly
for the most current data.

## Version Consistency Check

When releasing a new version or making changes across multiple repos, run:

```bash
uv run scripts/sync-routing.py --verify-versions --detail
```

This compares `registry.yaml` version against each local component's
`SKILL.md` / `pyproject.toml` version and flags any drifts.

The check is also available as a lifecycle closure step (see `registry.yaml`
`lifecycle.closure`).

| Task type | Indicators | Load first | Work principles |
|:----------|:-----------|:-----------|:----------------|
| **Research & plan** | Investigate, analyse, design, choose, compare, evaluate | `pre-action-research` | §1.1 Research first, propose a solution, await approval |
| **Modify system** | Change config, restart, upgrade, migrate, refactor, delete, fix, install, uninstall | `change-safeguard` | §2.1 Backup first, baseline record §3.1 Five-point post-scan |
| **Deploy service** | Deploy, install service, start service, register, expose port, go live, publish | `deploy-register` | §4.2 Register immediately, attach health checks |
| **Wrap up & close** | Finish, summarise, clean, end, verify, deliver | `work-closure-check` | §4.3 Confirm success first, clean after user confirms |
| **Uncertain / mixed** | Task spans multiple categories | Load all matching skills | Combine checklists from each category |

> **Agent note:** The classification is based on semantic understanding of the
> task, not keyword matching. If a task has characteristics of multiple types
> (e.g. "upgrade a service" is both modify + deploy), load the skills for
> each applicable type.

## Unified Workflow

```
Task arrives
    │
    ▼
Load execution-framework (this skill)
    │
    ├── Run scripts/sync-routing.py --diff (auto-check)
    │   └── If gaps → report to user → ask approval → --apply
    │
    ▼
Read routing.yaml / classification table
    │
    ▼
Identify task type from table
    │
    ├── Research & plan  → load pre-action-research
    ├── Modify system    → load change-safeguard
    ├── Deploy service   → load deploy-register
    ├── Wrap up & close  → load work-closure-check
    └── Uncertain/mixed  → load all matching skills
    │
    ▼
Execute the loaded skill's checklist
    │
    ▼
Proceed with task work
```

## Why This Approach

Instead of each skill independently listening for specific keywords (which is
language-dependent and fragile), a single framework skill uses semantic
understanding — the agent reads the classification table and decides which
type the task belongs to. This is:

- **Language-independent** — works for any language
- **Maintainable** — one classification table, not N keyword lists
- **Extensible** — new task types just need a new row in the table
- **Self-evolving** — `sync-routing.py` detects and suggests new skills
- **Failsafe** — the "Uncertain / mixed" row catches everything else

## Future Scope (Phase 2/3)

- `--scope all`: Scan all Hermes skills (`~/.hermes/skills/`), MCP servers
  (`config.yaml`), CLI tools (`hermes`, `officecli`, etc.), and toolchains
  — not just astra registry
- Auto-suggest routing categories based on skill/MCP/CLI descriptions
- "Capability reminder": when starting a task, suggest relevant tools
  from the full ecosystem that the agent hasn't loaded yet

## Pitfalls

1. **Do not skip the auto-check.** Run `sync-routing.py --diff` on first load
   to ensure the routing table is current.
2. **Do not skip classification.** The table is the core of this skill. Read
   `routing.yaml` every time, even for seemingly simple tasks.
3. **Do not load this skill and then skip loading sub-skills.** The framework
   routes to sub-skills — it does not replace their checklists.
4. **"Uncertain" is not failure.** If a task doesn't clearly fit one category,
   load all matching skills. Over-checking is safer than under-checking.
5. **Do not maintain keyword lists in sub-skills.** All routing goes through
   this framework. Sub-skill trigger sections can be minimal or removed.
6. **routing.yaml is the source of truth.** The markdown table in SKILL.md is
   a snapshot reference. Always defer to `routing.yaml` for current data.
