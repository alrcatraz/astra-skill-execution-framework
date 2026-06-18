# astra-skill-execution-framework

Task classification and routing for Hermes Agent. A single entry point that
classifies any task by type and routes to the correct workflow skill —
eliminating language-dependent keyword matching.

**Self-evolving:** `sync-routing.py` automatically detects new skills in the
astra ecosystem and suggests updates to the routing table.

## Features

- **Language-independent routing** — uses semantic understanding, not keyword lists
- **One classification table** — maps task types to work principles and sub-skills
- **Self-evolving** — `sync-routing.py` detects new skills and suggests routing entries
- **Failsafe** — "Uncertain / mixed" row catches everything that doesn't fit neatly
- **Extensible** — new task types get one row in the table, no keyword maintenance

## Architecture

```
astra-skill-execution-framework/
├── SKILL.md                  ← Agent instructions: reads routing.yaml, runs auto-check
├── routing.yaml              ← Machine-readable routing table (script can update)
├── scripts/
│   └── sync-routing.py       ← Self-evolution engine
└── README.md / LICENSE / .gitignore
```

### routing.yaml

The classification table lives in structured YAML, not Markdown. This means:
- Machine-readable (script can parse, diff, and update)
- Human-readable (agents read it for classification decisions)
- Versioned — separate from SKILL.md, can track changes independently

### sync-routing.py

The self-evolution engine that keeps the routing table current:

| Command | Effect |
|:--------|:-------|
| `--diff` (default) | Check for gaps (silent if current, reports if gaps) |
| `--detail` | Full report with category suggestions |
| `--apply` | Interactive apply (prompts for each new skill) |
| `--auto --apply` | Non-interactive apply (for cron, no prompts) |
| `--cron-check` | Exit 0 if clean, 1 if gaps (for cron monitoring) |

The script:
1. Scans `astra-aiagent-infra/registry.yaml` for all `type: skill` components
2. Compares against `routing.yaml` entries
3. Detects: **unregistered skills** (in registry, not in routing) and **orphans** (in routing, not in registry)
4. Suggests routing categories based on skill name + description heuristics
5. Uses timestamp cache — if routing.yaml is newer than registry.yaml, exits instantly

## How Auto-Check Works

When the agent loads this skill, it automatically runs `sync-routing.py --diff`:

```
Load execution-framework
    │
    ├── Run sync-routing.py --diff
    │   ├── routing.yaml newer → silent pass (milliseconds)
    │   └── registry.yaml newer → full diff → report gaps
    │
    ▼
Proceed with task classification
```

If gaps are found, the agent reports them and offers to run `--apply`.

## Cron Fallback

For users who prefer scheduled automation, set up a daily cron job:

```bash
# Daily check — only notifies when gaps are found
0 9 * * * cd /path/to/astra-skill-execution-framework && \
  uv run scripts/sync-routing.py --cron-check \
  || (echo "Routing table has gaps" | mail -s "execution-framework" admin@example.com)

# Daily auto-sync — applies new skills without manual approval
0 10 * * * cd /path/to/astra-skill-execution-framework && \
  uv run scripts/sync-routing.py --auto --apply
```

> **Note:** The built-in auto-check (when the skill loads) is the primary
> mechanism. Cron is optional and suitable for headless environments.

## Install

Copy `SKILL.md` and `routing.yaml` to your Hermes profile's `skills/` directory:

```bash
mkdir -p ~/.hermes/profiles/default/skills/execution-framework
cp SKILL.md ~/.hermes/profiles/default/skills/execution-framework/
cp routing.yaml ~/.hermes/profiles/default/skills/execution-framework/
```

The `scripts/` directory is optional — the auto-check uses it when available.
Without it, the skill still works (just without the self-evolution feature).

## Dependencies

| Repository | Resource | Required | Purpose |
|:-----------|:---------|:--------:|:--------|
| [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) | Ecosystem workflow skills | Optional | Combined with pre-action-research, change-safeguard, deploy-register, work-closure-check |
| [astra-aiagent-infra](https://github.com/alrcatraz/astra-aiagent-infra) | registry.yaml | Optional | Required for sync-routing.py (auto-detect new skills) |

## License

MIT — see [LICENSE](LICENSE).

---

## 中文版

## 功能

- **语言无关的任务路由** — 基于语义理解，不依赖关键词列表
- **单一分类表** — 将任务类型映射到对应的工作原则和子 skill
- **自我进化** — `sync-routing.py` 自动检测新加入生态的 skill 并建议加入路由表
- **安全兜底** — "不确定/混合"行覆盖一切无法精确定义的任务
- **可扩展** — 新增任务类型只需在表里加一行，无需维护关键词

## 自动检查机制

当 Agent 加载此 skill 时，会自动运行 `sync-routing.py --diff`：

1. **时间戳缓存** — 如果 routing.yaml 比 registry.yaml 更新，立即静默通过
2. **发现差距** — 列出未注册的 skill 和孤立条目
3. **报告+建议** — 向用户展示差距，询问是否 `--apply`

## Cron 回退方案

对于需要在无交互环境中自动执行（如非交互式部署）的场景，可以设置定时任务：

```bash
# 每日检查——仅在发现差距时通知
0 9 * * * cd /path/to/astra-skill-execution-framework && \
  uv run scripts/sync-routing.py --cron-check \
  || (echo "路由表需要更新" | mail -s "execution-framework" admin@example.com)

# 每日自动同步——无需人工确认，直接应用新 skill
0 10 * * * cd /path/to/astra-skill-execution-framework && \
  uv run scripts/sync-routing.py --auto --apply
```

> 注意：skill 加载时的内建自动检查是主要机制，cron 是可选的，适用于无
> 人值守环境。

## 安装

将 `SKILL.md` 和 `routing.yaml` 复制到 Hermes profile 的 `skills/` 目录下：

```bash
mkdir -p ~/.hermes/profiles/default/skills/execution-framework
cp SKILL.md ~/.hermes/profiles/default/skills/execution-framework/
cp routing.yaml ~/.hermes/profiles/default/skills/execution-framework/
```

`scripts/` 目录为可选——自进化功能需要该目录，但即使没有`scripts/`，
skill 的路由核心功能仍然正常工作。
