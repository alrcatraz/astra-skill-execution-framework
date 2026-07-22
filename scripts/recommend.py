#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Execution Framework — Recommendation Engine                 ║
║                                                              ║
║  Takes a natural language task description and returns       ║
║  ranked workflow steps + background rules.                   ║
║                                                              ║
║  Usage:                                                      ║
║    recommend.py \"帮我把 Nginx 配置成反向代理\"                 ║
║    recommend.py --json \"push this repo\"                      ║
║    recommend.py --interactive                                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import re
import sys
from pathlib import Path
from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Tuple

# ── Paths ────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
INDEX_PATH = SKILL_DIR / "skills_index.json"
ROUTING_PATH = SKILL_DIR / "routing.yaml"


# ── Loaders ──────────────────────────────────────────────────


def load_index() -> dict:
    """Load skills_index.json."""
    if not INDEX_PATH.exists():
        print(f"ERROR: {INDEX_PATH} not found. Run `sync-routing.py --scan --write-index` first.",
              file=sys.stderr)
        sys.exit(2)
    with open(INDEX_PATH) as f:
        return json.load(f)


def tokenise(text: str) -> List[str]:
    """Split task description into lowercase tokens for matching."""
    text = text.lower()
    # Keep Chinese characters as-is, split English on whitespace/punctuation
    tokens = []
    for part in re.split(r"[,，。.！!？?、；;：:\s()（）\[\]【】{}]+", text):
        part = part.strip()
        if part:
            tokens.append(part)
    return tokens


# ── Matching Engine ──────────────────────────────────────────


def match_indicators(tokens: List[str], indicators: List[str]) -> Tuple[List[str], float]:
    """
    Match task tokens against a list of indicator phrases.
    Returns (matched_indicators, score 0.0-1.0).
    """
    text = " ".join(tokens)
    matched = []
    for indicator in indicators:
        if indicator in text:
            matched.append(indicator)
    if not indicators:
        return ([], 0.0)
    score = len(matched) / max(len(indicators), 1)
    return (matched, round(min(score, 1.0), 2))


def recommend(task: str, index: dict) -> Dict[str, Any]:
    """
    Main recommendation function.
    Returns structured recommendation with workflow and background.
    """
    tokens = tokenise(task)
    text = " ".join(tokens)
    workflow_results = []

    # Build a name -> index map for fast lookup
    index_map = {s["name"]: s for s in index.get("skills", [])}

    for wf in index.get("workflow", []):
        wf_id = wf.get("id", "?")
        label = wf.get("label", wf_id)
        is_always = wf.get("always", False)
        when_indicators = wf.get("when", [])
        order = wf.get("order", 99)

        # Step-level matching
        step_matched, step_score = match_indicators(tokens, when_indicators)

        # Per-skill evaluation: only include skills with matching indicators
        all_step_skills = [s for s in wf.get("skills", []) if isinstance(s, dict)]
        matched_skills = []

        for s in all_step_skills:
            skill_name = s.get("name", "")
            skill_indicators = s.get("indicators", [])
            indexed = index_map.get(skill_name)

            # Collect all indicators for this skill
            all_skill_inds = list(skill_indicators)  # from routing.yaml

            # Also check tags and description from index
            if indexed:
                tags = indexed.get("tags", [])
                if isinstance(tags, list):
                    all_skill_inds.extend(tags)
                # Description intentionally excluded from per-skill matching
                # to avoid noise from generic keywords in prose text.
                # Only explicit indicators and tags are used.
                all_skill_inds.extend(indexed.get("all_indicators", []))

            # Deduplicate and match
            all_skill_inds = sorted(set(i for i in all_skill_inds if i))
            ind_matched, ind_score = match_indicators(tokens, all_skill_inds)

            # Include skill if:
            # - always step: include all skills
            # - step indicators match and skill indicators match
            # - no skill indicators but the step itself matched
            if is_always:
                matched_skills.append(skill_name)
            elif (ind_score > 0 or ind_matched) and len(all_skill_inds) > 0:
                matched_skills.append(skill_name)
            elif not all_skill_inds and step_score > 0:
                # Skill has no indicators at all — only include if step matches
                matched_skills.append(skill_name)
            # Skills with generic/no indicators that don't match get excluded

        # Step confidence: max of step-level match and individual skill matches
        best_skill_score = 0.0
        for s in all_step_skills:
            skill_name = s.get("name", "")
            skill_indicators = s.get("indicators", [])
            _, ss = match_indicators(tokens, skill_indicators)
            if ss > best_skill_score:
                best_skill_score = ss

        final_score = max(step_score, best_skill_score)

        # Always steps are always included
        if is_always:
            workflow_results.append({
                "workflow_id": wf_id,
                "label": label,
                "order": order,
                "always": True,
                "confidence": 1.0,
                "matched_indicators": [],
                "skills": matched_skills,
            })
            continue

        # Only include conditional steps if they matched
        if final_score > 0 or step_matched:
            workflow_results.append({
                "workflow_id": wf_id,
                "label": label,
                "order": order,
                "always": False,
                "confidence": final_score,
                "matched_indicators": sorted(set(step_matched)),
                "skills": matched_skills,
            })

    # Sort by order, then by confidence descending
    workflow_results.sort(key=lambda x: (x["order"], -x["confidence"]))

    # Background rules are always included
    background = index.get("background", [])

    # Build skill details for the recommended skills
    skill_details = {}
    for wf_result in workflow_results:
        for skill_name in wf_result["skills"]:
            if skill_name not in skill_details:
                for indexed_skill in index.get("skills", []):
                    if indexed_skill["name"] == skill_name:
                        skill_details[skill_name] = {
                            "name": skill_name,
                            "description": indexed_skill.get("description", "")[:120],
                            "tags": indexed_skill.get("tags", []),
                            "version": indexed_skill.get("version", ""),
                        }
                        break

    return {
        "task": task,
        "tokens": tokens,
        "workflow": workflow_results,
        "background": background,
        "skill_details": skill_details,
    }


# ── Formatters ───────────────────────────────────────────────


def format_recommendation(rec: dict) -> str:
    """Format recommendation as human-readable text."""
    lines = []
    lines.append(f"🧭 能力推荐：{rec['task']}")
    lines.append("")

    if rec["workflow"]:
        lines.append("**工作流步骤（按顺序）：**")
        for wf in rec["workflow"]:
            confidence = wf["confidence"]
            always_tag = " 🔒(必选)" if wf.get("always") else ""
            bar = "▓" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
            lines.append(f"  [{wf['order']}] {wf['label']}{always_tag}")
            lines.append(f"      {bar} {confidence:.0%}")
            if wf["matched_indicators"]:
                lines.append(f"      命中: {', '.join(wf['matched_indicators'][:5])}")
            skills_display = wf['skills']
            if len(skills_display) > 8:
                skills_display = skills_display[:7] + [f'... 以及 {len(skills_display)-7} 个其他技能']
            lines.append(f"      技能: {', '.join(skills_display)}")
    else:
        lines.append("  ⚠️  未匹配到任何工作流步骤")

    if rec["background"]:
        lines.append("")
        lines.append("**背景纪律（全程生效）：**")
        for bg in rec["background"]:
            mode_tag = "🔧" if bg.get("mode") == "active" else "🔒"
            phases = ", ".join(bg.get("phases", []))
            lines.append(f"  {mode_tag} `{bg.get('id', '?')}` — {bg.get('label', '')}")
            lines.append(f"     生效: {phases}")
            for rule in bg.get("rules", []):
                lines.append(f"     · {rule}")

    if rec["skill_details"]:
        lines.append("")
        lines.append("**技能详情：**")
        for name, detail in rec["skill_details"].items():
            lines.append(f"  · `{name}` — {detail['description'][:80]}")

    return "\n".join(lines)


def format_json(rec: dict) -> str:
    """Format as JSON."""
    return json.dumps(rec, indent=2, ensure_ascii=False)


# ── MAIN ─────────────────────────────────────────────────────


def parse_args(argv: List[str]) -> Namespace:
    parser = ArgumentParser(description="Recommend skills for a task")
    parser.add_argument("task", nargs="?", default="",
                        help="Task description in natural language")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Output as JSON")
    parser.add_argument("--interactive", action="store_true", default=False,
                        help="Interactive mode: prompt for tasks")
    parser.add_argument("--write-steps", action="store_true", default=False,
                        help="Write workflow steps to ~/.hermes/persistent/recommend_steps.json")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])

    index = load_index()

    if args.interactive:
        print("🧭 Execution Framework — Recommendation Engine")
        print("输入任务描述（空行退出）：")
        while True:
            try:
                task = input("\n> ").strip()
                if not task:
                    break
                rec = recommend(task, index)
                print()
                print(format_recommendation(rec))
            except (EOFError, KeyboardInterrupt):
                break
        return 0

    task = args.task
    if not task:
        print("Usage: recommend.py <task description>", file=sys.stderr)
        print("       recommend.py --interactive", file=sys.stderr)
        return 1

    rec = recommend(task, index)

    # ── Always write workflow steps to persistent file ──
    # The plugin reads this in pre_llm_call to inject step reminders.
    steps_file = Path.home() / ".hermes" / "recommend_steps.json"
    steps_file.parent.mkdir(parents=True, exist_ok=True)
    steps_data = {
        "task": rec["task"],
        "workflow": [
            {
                "id": wf["workflow_id"],
                "label": wf["label"],
                "order": wf["order"],
                "always": wf.get("always", False),
                "confidence": wf["confidence"],
                "skills": wf.get("skills", []),
            }
            for wf in rec["workflow"]
        ],
        "background": [
            {
                "id": bg.get("id", "?"),
                "label": bg.get("label", ""),
                "phases": bg.get("phases", []),
            }
            for bg in rec["background"]
        ],
    }
    with open(steps_file, "w") as f:
        json.dump(steps_data, f, indent=2, ensure_ascii=False)

    if args.json:
        print(format_json(rec))
    else:
        print(format_recommendation(rec))

    return 0


if __name__ == "__main__":
    sys.exit(main())
