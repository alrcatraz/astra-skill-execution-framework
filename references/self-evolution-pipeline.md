# Self-Evolution Pipeline — Design Rationale

## Why This Exists

The routing table (`routing.yaml`) maps task types to sub-skills. As the astra
ecosystem grows, new skills appear in `registry.yaml` but the routing table
stays the same — until someone remembers to update it.

The self-evolution pipeline bridges that gap by detecting stale routing data
and suggesting updates automatically, on skill load.

## Architecture

```
Skill loads
    │
    ▼
stat(routing.yaml) vs stat(registry.yaml)  ← timestamp cache
    │
    ├── routing newer → silent pass (zero overhead, <1ms)
    │
    └── registry newer → full diff
            │
            ├── unregistered skills (in registry, not in routing)
            ├── orphans (in routing, not in registry)
            └── category suggestions (keyword heuristic)
                    │
                    ▼
            User reviews → approves → sync-routing.py --apply → writes routing.yaml
```

## Design Decisions

### 1. Timestamp cache (not hash-based)

**Problem:** Full diff on every skill load is wasteful.
**Solution:** Compare mtime. If routing.yaml is newer than registry.yaml,
nothing could have changed — skip immediately.

**Trade-off:** `touch registry.yaml` invalidates the cache. Acceptable: the
diff is cheap (<100ms even with 50 skills).

### 2. Keyword suggestion (not LLM)

**Problem:** "Which category does this new skill belong to?"
**Solution:** Weighted keyword matching on skill name + description.
Name matches count double (more intentional signal).

**Why not LLM:** The suggestion is advisory, not authoritative.
Deterministic heuristics are faster, predictable, and debuggable.

### 3. Interactive apply (not auto)

**Problem:** Auto-adding every detected skill could misroute.
**Solution:** `--diff` reports, `--apply` asks per-skill.
`--auto --apply` available for headless environments.

## Phase 2/3 Extension

```python
# Current (Phase 1): --scope astra → only scan registry.yaml
# Future (Phase 2):  --scope all  → add Hermes skills + MCP + CLI
# Future (Phase 3):  capability reminder → suggest tools before agent works
```

To add scope: implement a loader function, merge into diff engine, expand
CATEGORY_SIGNALS if new categories needed.

## Maintenance

When adding keywords to CATEGORY_SIGNALS in sync-routing.py:
- Add words from skill descriptions, not just names
- Prefer noun forms ("deployment" > "deploying")
- Include synonyms common in the ecosystem
