---
name: execution-framework
description: >
  Task classification and routing. Use this when starting any task — research,
  plan, modify, deploy, fix, analyse, investigate, close — to identify the
  correct work principles and supporting skills for this type of work.
  Self-evolving: auto-detects new skills via sync-routing.py and suggests
  routing table updates.
category: devops
version: 2.0.0
tags: [routing, classification, workflow]
---

# Execution Framework

A single entry point for any task. Classify the task, then follow the
corresponding workflow checklist.

**Canonical source:** `~/Projects/astra/astra-skill-execution-framework/`
— this Hermes copy is a deployment. Update the project repo first, then
recopy SKILL.md, routing.yaml, and scripts/ here.

## Trigger Conditions

Loaded when starting almost any task:
- Research, plan, analyse, design, propose
- Modify, configure, fix, repair, debug
- Deploy, install, register, set up, publish
- Close, wrap up, summarise, clean up
- Investigate, diagnose, troubleshoot, audit

When in doubt, load this skill — the overhead is reading one table and
following one checklist; the benefit is never skipping a necessary step.

## Auto-Check (Self-Evolution)

On load, run `scripts/sync-routing.py --diff` to verify the routing table is
current (only if the script is present in the skill directory):

1. **Timestamp cache** — compares `routing.yaml` mtime vs `registry.yaml` mtime
   - Routing newer → silent pass (zero overhead)
   - Registry newer → full diff → report gaps
2. **Gap report** — lists unregistered skills and orphans
3. **If gaps found** → present to user, ask approval, then
   `scripts/sync-routing.py --apply`

If `scripts/` is not present, this step is skipped — skill falls back to
the static routing table below.

## Version Consistency Check

When releasing a new version or making cross-repo changes, verify version
alignment:

```bash
cd ~/Projects/astra/astra-skill-execution-framework
uv run scripts/sync-routing.py --verify-versions --detail
```

This compares `registry.yaml` version against each local component's
`SKILL.md` / `pyproject.toml` / `AGENTS.md` / `README.md` version field,
flagging any drifts. See `work-closure-check` stage ⑦ for commit workflow
integration.

The check is also registered as a lifecycle closure hook in `registry.yaml`
(trigger: registry.yaml or SKILL.md modified).

## Classification Table

Read `routing.yaml` for the definitive source. The table below is a snapshot.

| Task type | Indicators | Load first | Work principles |
|:----------|:-----------|:-----------|:----------------|
| **Research & plan** | Investigate, analyse, design, choose, compare, evaluate | `pre-action-research` | §1.1 Research first, propose, await approval |
| **Modify system** | Change config, restart, upgrade, migrate, refactor, delete, fix, install | `change-safeguard` | §2.1 Backup first, baseline §3.1 Post-scan |
| **Deploy service** | Deploy, install service, start, register, expose, publish | `deploy-register` | §4.2 Register immediately, health checks |
| **Wrap up & close** | Finish, summarise, clean, end, verify, deliver | `work-closure-check` | §4.3 Confirm success, clean after user |
| **Uncertain / mixed** | Spans multiple categories | Load all matching | Combine checklists |

> Semantic understanding, not keyword matching. If a task is both modify +
> deploy, load both skills.

## Unified Workflow

```
Task arrives → Load execution-framework
  ├── Run scripts/sync-routing.py --diff (if present)
  │     └─ If gaps → report → ask approval → --apply
  ├── Read routing.yaml → identify task type
  ├── Load sub-skill's checklist
  └── Proceed with task work
```

## Phase 2/3 (Future)

- `--scope all`: scan Hermes skills, MCP servers, CLI tools — not just astra
- Capability reminder: before task work, suggest relevant unloaded tools

## Pitfalls

1. **Do not skip the auto-check** on first load.
2. **Do not skip classification** — read routing.yaml every time.
3. **Do not substitute for sub-skills** — framework routes; sub-skills provide checklists.
4. **"Uncertain" is not failure** — load all matching skills.
5. **routing.yaml is the source of truth**, not the markdown table.
