#!/usr/bin/env python3
"""
Self-evolution engine for execution-framework routing table.

Scans astra registry.yaml for skill components, compares against routing.yaml,
and reports / applies gaps.

Usage (from the project root, where routing.yaml lives):
  uv run scripts/sync-routing.py --diff     # Check for gaps (default)
  uv run scripts/sync-routing.py --detail   # Full report with category suggestions
  uv run scripts/sync-routing.py --apply    # Interactive apply (user confirms each)
  uv run scripts/sync-routing.py --cron-check  # Cron mode: exit 0 if clean, 1 if gaps

Note: This script is designed to run from the project directory
  ~/Projects/astra/astra-skill-execution-framework/
where routing.yaml and the sibling registry.yaml are available.

Full source: ~/Projects/astra/astra-skill-execution-framework/scripts/sync-routing.py
"""
import sys
print("sync-routing.py: Run from the project directory, not from Hermes.")
print("  cd ~/Projects/astra/astra-skill-execution-framework")
print("  uv run scripts/sync-routing.py --diff")
sys.exit(1)
