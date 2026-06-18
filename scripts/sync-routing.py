#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Execution Framework — Routing Sync Engine                  ║
║                                                              ║
║  Scans astra registry.yaml for skill components, compares    ║
║  against routing.yaml, and reports / applies gaps.           ║
║                                                              ║
║  Usage:                                                      ║
║    sync-routing.py [--diff]          Check routing gaps      ║
║                                        (default)             ║
║    sync-routing.py --detail          Full report with        ║
║                                        category suggestions  ║
║    sync-routing.py --apply           Apply suggested changes ║
║                                        (requires confirmed)  ║
║    sync-routing.py --cron-check      Cron mode: exit 0 if    ║
║                                        clean, 1 if gaps      ║
║    sync-routing.py --verify-versions Check version           ║
║                                        consistency across    ║
║                                        registry + local repo ║
║    sync-routing.py --scope astra     Only astra registry     ║
║                                        (default)             ║
║    sync-routing.py --scope all       All agent tools (future)║
║                                                              ║
║  Auto-mode (from SKILL.md): run --diff; if gaps found,       ║
║  ask user before --apply.                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import sys
import yaml
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ROUTING_PATH = SKILL_DIR / "routing.yaml"
ECOSYSTEM_PARENT = SKILL_DIR.parent  # parent dir holding all astra repos

# Resolve the astra-aiagent-infra registry. Try multiple layouts.
REGISTRY_CANDIDATES = [
    SKILL_DIR / ".." / "astra-aiagent-infra" / "registry.yaml",   # sibling dir (local dev)
    SKILL_DIR.parent / "astra-aiagent-infra" / "registry.yaml",   # same parent
    Path.cwd() / "astra-aiagent-infra" / "registry.yaml",         # cwd
]

# ── Exit codes ───────────────────────────────────────────────

EXIT_CLEAN = 0
EXIT_GAPS = 1
EXIT_DRIFT = 1  # same as gaps — actionable issue
EXIT_ERROR = 2

# ── Known non-routable meta-skills ────────────────────────────

SKIP_SKILLS = {"execution-framework", "astra-sre"}

# ── Category slot weights ─────────────────────────────────────

CATEGORY_SIGNALS: Dict[str, List[str]] = {
    "research-plan": [
        "research", "investigate", "investigation", "analyse", "analysis",
        "analytical", "plan", "planning", "proposal", "propose",
        "design", "evaluate", "evaluation", "study", "survey",
        "compare", "comparison", "feasibility",
    ],
    "modify-system": [
        "safeguard", "backup", "change", "modify", "modification",
        "fix", "repair", "patch", "refactor", "refactoring",
        "upgrade", "migrate", "migration", "configure", "configuration",
        "install", "uninstall", "delete", "remove",
    ],
    "deploy-service": [
        "deploy", "deployment", "register", "registration",
        "install service", "service", "launch", "publish",
        "expose", "go live", "enable", "start",
    ],
    "wrap-up": [
        "close", "closure", "wrap up", "wrap-up", "clean",
        "cleanup", "clean up", "finish", "summarise", "summary",
        "verify", "verification", "deliver", "complete", "completion",
        "conclude", "conclusion",
    ],
}

# ── SemVer helpers ────────────────────────────────────────────


def parse_semver(text: str) -> Tuple[int, int, int, str, str]:
    """
    Parse SemVer 2.0.0: MAJOR.MINOR.PATCH[-pre][+build]
    Returns (major, minor, patch, pre, build).
    """
    m = re.match(
        r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9._-]+))?(?:\+([a-zA-Z0-9._-]+))?$",
        text.strip(),
    )
    if not m:
        raise ValueError(f"Cannot parse SemVer: {text!r}")
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        m.group(4) or "",
        m.group(5) or "",
    )


def semver_base(text: str) -> str:
    """Strip pre-release and build metadata — return 'X.Y.Z'."""
    major, minor, patch, _, _ = parse_semver(text)
    return f"{major}.{minor}.{patch}"


def semver_build(text: str) -> str:
    """Return build metadata suffix, empty if none."""
    _, _, _, _, build = parse_semver(text)
    return build


def semver_compare(reported: str, local: str) -> str:
    """
    Compare two versions. Returns a status label.
    """
    try:
        base_reported = semver_base(reported)
        base_local = semver_base(local)
    except ValueError:
        return "⚠  invalid"
    if base_reported == base_local:
        if reported == local:
            return "✅  match"
        build = semver_build(local)
        if build:
            return f"📝  local suffix ({build})"
        return "⚠  format diff"
    return f"❌  DRIFT: registry={base_reported} ≠ skill={base_local}"


# ── Helpers ──────────────────────────────────────────────────


def find_registry() -> Optional[Path]:
    """Find the closest registry.yaml."""
    for p in REGISTRY_CANDIDATES:
        resolved = p.resolve()
        if resolved.exists():
            return resolved
    return None


def load_yaml(path: Path) -> dict:
    """Load a YAML file safely, returning empty dict on error."""
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def write_yaml(data: dict, path: Path) -> None:
    """Write structured YAML with human-friendly formatting."""
    with open(path, "w") as f:
        f.write("# ══════════════════════════════════════════════════════════════\n")
        f.write("# Execution Framework — Routing Table\n")
        f.write("# ══════════════════════════════════════════════════════════════\n")
        f.write("#\n")
        f.write("# Auto-generated by sync-routing.py\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#\n")
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_timestamp(path: Path) -> float:
    """Get file modification time, or 0 if file doesn't exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


# ── Registry loaders ─────────────────────────────────────────


def load_registry_skills(registry_path: Path) -> List[dict]:
    """
    Return list of skill-type components from registry.yaml
    (used by routing diff engine).
    """
    reg = load_yaml(registry_path)
    components = reg.get("components", [])
    skills = []
    for c in components:
        if c.get("type") != "skill":
            continue
        name = c.get("name", "")
        if name in SKIP_SKILLS:
            continue
        skills.append(c)
    return skills


def load_all_components(registry_path: Path) -> List[dict]:
    """
    Return ALL components from registry.yaml (any type).
    Used by version verification.
    """
    reg = load_yaml(registry_path)
    components = reg.get("components", [])
    result = []
    for c in components:
        name = c.get("name", "")
        if name in SKIP_SKILLS:
            # Still include these for version check, just don't route them
            pass
        result.append(c)
    return result


def load_routing(routing_path: Path) -> Tuple[List[dict], Dict[str, str]]:
    """
    Load routing.yaml.
    Returns (routing_entries, skill_map)
    where skill_map is {astra_skill_name: type_label}
    """
    data = load_yaml(routing_path)
    entries = data.get("routing", [])
    skill_map: Dict[str, str] = {}
    for entry in entries:
        for s in entry.get("skills", []):
            astra_name = s.get("astra_skill")
            if astra_name:
                skill_map[astra_name] = entry["type"]
            skill_name = s.get("name")
            if skill_name:
                skill_map[skill_name] = entry["type"]
    return entries, skill_map


# ── Category suggestion engine ───────────────────────────────


def suggest_category(name: str, description: str) -> Tuple[str, float]:
    """
    Suggest a routing category for a skill based on its name and description.
    Returns (category_type, confidence_score 0.0-1.0).
    """
    text = f"{name} {description}".lower()

    scores: Dict[str, int] = {}
    for category, signals in CATEGORY_SIGNALS.items():
        score = 0
        for signal in signals:
            if signal in text:
                score += 1
                if signal in name.lower() or signal.replace(" ", "-") in name.lower():
                    score += 0.5
        scores[category] = score

    if not scores or max(scores.values()) == 0:
        return ("uncertain", 0.0)

    best = max(scores, key=scores.get)
    best_score = scores[best]
    total = sum(scores.values())
    confidence = best_score / max(total, 1)

    type_hints_in_name = sum(1 for c, s in scores.items() if s > 0)
    if type_hints_in_name <= 2 and best_score >= 2:
        confidence = min(1.0, confidence + 0.2)

    return (best, round(confidence, 2))


# ── Diff Engine (routing table) ──────────────────────────────


def diff_routing(registry_skills: List[dict],
                 registered_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Compare registry skills against routing table.
    Returns a structured diff report.
    """
    registered_set = set(registered_map.keys())
    registry_names = {s["name"] for s in registry_skills}

    # Find unregistered skills (in registry but not in routing)
    unregistered = []
    for s in registry_skills:
        name = s["name"]
        astra_name = f"astra-skill-{name}"
        repo_name = s.get("repo", "")
        repo_short = repo_name.split("/")[-1] if "/" in repo_name else repo_name

        in_routing = (
            name in registered_set
            or astra_name in registered_set
            or repo_short in registered_set
        )
        if not in_routing:
            suggested, confidence = suggest_category(
                name, s.get("description", "")
            )
            unregistered.append({
                "name": name,
                "repo": repo_name,
                "description": s.get("description", ""),
                "suggested_category": suggested,
                "confidence": confidence,
            })

    # Find orphans (in routing but no longer in registry)
    routing_names = set()
    for entry_name in registered_map:
        clean = entry_name.replace("astra-skill-", "")
        routing_names.add(clean)

    orphans = []
    for rn in sorted(routing_names):
        found = False
        for s in registry_skills:
            name = s["name"]
            repo = s.get("repo", "")
            repo_short = repo.split("/")[-1] if "/" in repo else repo
            if rn in (name, f"astra-skill-{name}", repo_short):
                found = True
                break
        if not found and rn not in SKIP_SKILLS:
            orphans.append(rn)

    return {
        "unregistered": unregistered,
        "orphans": sorted(orphans),
        "total_registry": len(registry_skills),
        "total_routed": len(routing_names),
    }


# ── Version verification engine ──────────────────────────────


# Files to check for version (in order of priority)
VERSION_FILES = ["SKILL.md", "AGENTS.md", "pyproject.toml", "README.md"]


def find_local_repo(repo_name: str) -> Optional[Path]:
    """
    Resolve a GitHub repo name (e.g. 'alrcatraz/astra-skill-foo')
    to a local directory path.
    """
    repo_short = repo_name.split("/")[-1] if "/" in repo_name else repo_name
    candidates = [
        ECOSYSTEM_PARENT / repo_short,
        SKILL_DIR.parent / repo_short,
        Path.cwd() / repo_short,
    ]
    for c in candidates:
        resolved = c.resolve()
        if resolved.is_dir():
            return resolved
    return None


def parse_version_file(path: Path) -> Optional[str]:
    """
    Parse version from a YAML-frontmatter file (SKILL.md, AGENTS.md)
    or pyproject.toml.
    Returns the version string, or None if not found.
    """
    if not path.exists():
        return None

    raw = path.read_text()

    if path.suffix in (".md", ".MD") or path.suffix == ".rst":
        # Try YAML frontmatter: ---\nkey: value\n---
        m = re.match(r"^---\s*\n(.*?)\n---", raw, re.DOTALL)
        if not m:
            return None
        try:
            front = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            return None
        if isinstance(front, dict):
            v = front.get("version")
            return str(v) if v else None
        return None

    elif path.suffix in (".toml",):
        # Parse pyproject.toml: [project]\nversion = "X.Y.Z"
        m = re.search(r'^\[project\]\s*\n(?:[^[]*\n)*?version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
        if m:
            return m.group(1)
        # More relaxed: just find any toml line
        m = re.search(r'^version\s*=\s*"([^"]+)"', raw, re.MULTILINE)
        return m.group(1) if m else None

    return None


def check_component_version(component: dict) -> Dict[str, Any]:
    """
    Check version consistency for one registry component.
    Returns dict with status fields.
    """
    name = component.get("name", "unknown")
    repo = component.get("repo", "")
    registry_version = component.get("version", "")

    # Find local repo
    local_dir = find_local_repo(repo)

    result = {
        "name": name,
        "repo": repo,
        "registry_version": registry_version,
        "local_version": None,
        "local_source": None,
        "status": "❌  no local repo",
        "error": None,
    }

    if local_dir is None:
        result["status"] = "❓  local repo not found"
        return result

    # Check version files in order
    for vf_name in VERSION_FILES:
        vf_path = local_dir / vf_name
        version = parse_version_file(vf_path)
        if version is not None:
            result["local_version"] = version
            result["local_source"] = vf_name
            break

    if result["local_version"] is None:
        result["status"] = "⚠  no version file found"
        return result

    if not registry_version:
        result["status"] = "⚠  registry has no version"
        return result

    # Compare
    try:
        result["status"] = semver_compare(registry_version, result["local_version"])
    except ValueError as e:
        result["status"] = "⚠  version parse error"
        result["error"] = str(e)

    return result


def verify_all_versions(components: List[dict]) -> Dict[str, Any]:
    """
    Run version check across all components.
    Returns structured report.
    """
    results = []
    for c in components:
        r = check_component_version(c)
        results.append(r)

    # Tally
    clean = sum(1 for r in results if r["status"].startswith("✅"))
    local = sum(1 for r in results if r["status"].startswith("📝"))
    drift = sum(1 for r in results if r["status"].startswith("❌"))
    warning = sum(1 for r in results if "⚠" in r["status"] or "❓" in r["status"])
    missing = sum(1 for r in results if "❌" in r["status"] and "DRIFT" not in r["status"])

    return {
        "results": results,
        "total": len(results),
        "clean": clean,
        "local_suffix": local,
        "drift": drift,
        "warnings": warning,
        "missing": missing,
    }


# ── Apply Engine ─────────────────────────────────────────────


def auto_approve(question: str) -> bool:
    """
    Interactively ask the user for approval.
    Returns True if approved.
    """
    try:
        resp = input(f"\n❓ {question} [y/N] ").strip().lower()
        return resp in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def apply_updates(diff: dict, auto: bool = False) -> Tuple[bool, List[str]]:
    """
    Apply routing table updates based on diff.
    Returns (success, messages).
    """
    messages: List[str] = []
    routing_data = load_yaml(ROUTING_PATH)
    entries = routing_data.get("routing", [])

    unregistered = diff.get("unregistered", [])
    if not unregistered:
        return True, ["Nothing to apply — no unregistered skills found."]

    applied = 0
    skipped = 0

    for item in unregistered:
        name = item["name"]
        desc = item["description"]
        suggested = item["suggested_category"]
        confidence = item["confidence"]
        astra_skill = f"astra-skill-{name}"

        label = f"New skill: {name} ({desc[:60]}{'...' if len(desc) > 60 else ''})"
        question = f"{label}\n  → Suggested category: {suggested} (confidence: {confidence})\n  Add to routing?"

        approved = auto or auto_approve(question)

        if not approved:
            messages.append(f"⏭  Skipped: {name}")
            skipped += 1
            continue

        target_entry = None
        for entry in entries:
            if entry["type"] == suggested:
                target_entry = entry
                break

        if target_entry is None:
            new_entry = {
                "type": suggested,
                "label": suggested.replace("-", " ").title(),
                "indicators": [],
                "skills": [{"name": name, "astra_skill": astra_skill}],
                "principles": "Auto-added by sync-routing.py",
            }
            entries.append(new_entry)
            messages.append(f"✅ Added: {name} → new category '{suggested}'")
        else:
            skills_list = target_entry.setdefault("skills", [])
            existing_names = {s.get("name") for s in skills_list}
            if name not in existing_names:
                skills_list.append({"name": name, "astra_skill": astra_skill})
                messages.append(f"✅ Added: {name} → category '{suggested}'")
            else:
                messages.append(f"⏭  Already present: {name}")
                skipped += 1

        applied += 1

    routing_data["routing"] = entries
    write_yaml(routing_data, ROUTING_PATH)
    messages.append(f"\n📝 Wrote {ROUTING_PATH} ({applied} added, {skipped} skipped)")
    return True, messages


# ── Formatters ───────────────────────────────────────────────


def format_diff(diff: dict, detail: bool = False) -> str:
    """Format routing diff report as human-readable text."""
    lines: List[str] = []
    unregistered = diff["unregistered"]
    orphans = diff["orphans"]

    lines.append(f"╔══ Routing Sync Report ══╗")
    lines.append(f"║  Registry skills : {diff['total_registry']:>3}")
    lines.append(f"║  Routed skills   : {diff['total_routed']:>3}")
    lines.append(f"╚══════════════════════════╝")

    if not unregistered and not orphans:
        lines.append("\n✨ Routing table is up to date — no gaps found.")
        return "\n".join(lines)

    if unregistered:
        lines.append(f"\n── Unregistered skills ({len(unregistered)} in registry, not in routing) ──")
        for item in unregistered:
            lines.append(f"\n  • {item['name']}")
            lines.append(f"    Repo: {item['repo']}")
            lines.append(f"    Desc: {item['description'][:100]}")
            if detail:
                suggested = item["suggested_category"]
                confidence = item["confidence"]
                lines.append(f"    ➜  Suggested: {suggested} (confidence: {confidence})")
            else:
                lines.append(f"    (run --detail for category suggestions)")

    if orphans:
        lines.append(f"\n── Orphaned entries ({len(orphans)} in routing, not in registry) ──")
        for o in orphans:
            lines.append(f"  • {o}")

    return "\n".join(lines)


def format_version_report(report: Dict[str, Any], detail: bool = False) -> str:
    """Format version verification report."""
    lines: List[str] = []
    results = report["results"]

    lines.append(f"╔══ Version Consistency Report ══╗")
    lines.append(f"║  Total components: {report['total']:>3}")
    lines.append(f"║  ✅  Match        : {report['clean']:>3}")
    lines.append(f"║  📝  Local suffix : {report['local_suffix']:>3}")
    lines.append(f"║  ❌  Drift        : {report['drift']:>3}")
    lines.append(f"║  ⚠   Warnings     : {report['warnings']:>3}")
    lines.append(f"╚═══════════════════════════════╝")

    if report["clean"] == report["total"]:
        lines.append("\n✨ All components have consistent versions.")
        return "\n".join(lines)

    lines.append("")
    for r in results:
        if r["status"].startswith("✅") or r["status"].startswith("📝"):
            if not detail:
                continue  # Hide clean items unless --detail

        name = r["name"]
        reg_v = r["registry_version"] or "—"
        loc_v = r["local_version"] or "—"
        src = f" ({r['local_source']})" if r["local_source"] else ""
        status = r["status"]
        is_clean = status.startswith("✅") or status.startswith("📝")
        is_drift = status.startswith("❌")
        is_warn = status.startswith("⚠")
        is_missing = status.startswith("❓")

        if is_clean and detail:
            lines.append(f"  {status}  {name:30s}  registry={reg_v:15s}  skill={loc_v}{src}")
        elif is_drift or is_warn:
            lines.append(f"  {status}  {name:30s}  registry={reg_v:15s}  skill={loc_v}{src}")
            if r.get("error"):
                lines.append(f"    ↳ {r['error']}")
        elif is_missing:
            lines.append(f"  {status:44s}  no local repo for {r['repo']}")

    return "\n".join(lines)


# ── MAIN ─────────────────────────────────────────────────────


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser(description="Routing table sync engine for execution-framework")
    parser.add_argument("--diff", action="store_true", default=True,
                        help="Check for gaps (default)")
    parser.add_argument("--detail", action="store_true", default=False,
                        help="Full report with category suggestions")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Apply suggested changes (interactive)")
    parser.add_argument("--auto", action="store_true", default=False,
                        help="Non-interactive apply (for cron, no prompts)")
    parser.add_argument("--cron-check", action="store_true", default=False,
                        help="Cron mode: exit 0 if clean, 1 if gaps")
    parser.add_argument("--verify-versions", action="store_true", default=False,
                        help="Check version consistency across registry + local repos")
    parser.add_argument("--scope", choices=["astra", "all"], default="astra",
                        help="Scan scope: astra (now) or all (future)")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])

    # ── Find registry ──
    registry_path = find_registry()
    if registry_path is None:
        print("ERROR: Cannot find registry.yaml. Checked:")
        for c in REGISTRY_CANDIDATES:
            print(f"  - {c.resolve()}")
        return EXIT_ERROR

    # ── Version verification mode ──
    if args.verify_versions:
        components = load_all_components(registry_path)
        report = verify_all_versions(components)
        print(format_version_report(report, detail=args.detail))
        if report["drift"] > 0:
            return EXIT_DRIFT
        return EXIT_CLEAN

    # ── Timestamp cache check ──
    routing_mtime = get_timestamp(ROUTING_PATH)
    registry_mtime = get_timestamp(registry_path)

    if not args.apply:
        if routing_mtime >= registry_mtime and routing_mtime > 0:
            if args.cron_check:
                return EXIT_CLEAN
            if not args.detail:
                print("✓ Routing table is current (no changes since last sync).")
                return EXIT_CLEAN

    # ── Load and diff ──
    registry_skills = load_registry_skills(registry_path)
    route_entries, registered_map = load_routing(ROUTING_PATH)
    diff = diff_routing(registry_skills, registered_map)

    has_gaps = bool(diff["unregistered"] or diff["orphans"])

    # ── Cron mode ──
    if args.cron_check:
        if has_gaps:
            print(format_diff(diff, detail=True))
            return EXIT_GAPS
        return EXIT_CLEAN

    # ── Apply mode ──
    if args.apply:
        if not has_gaps:
            print("✨ Routing table is up to date. Nothing to apply.")
            return EXIT_CLEAN
        print(format_diff(diff, detail=True) + "\n")
        success, msgs = apply_updates(diff, auto=args.auto)
        for m in msgs:
            print(m)
        return EXIT_CLEAN if success else EXIT_ERROR

    # ── Diff mode (default) ──
    print(format_diff(diff, detail=args.detail))

    if has_gaps:
        print("\n── Suggestions ──")
        print("  Run `sync-routing.py --apply` to add unregistered skills")
        print("  Run `sync-routing.py --detail` for more details")
        return EXIT_GAPS

    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
