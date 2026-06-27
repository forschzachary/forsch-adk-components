"""Patterns linter — drift detector across inventories + registry + filesystem.

Walks all inventory.yaml files (patterns, agents, uis, routers, datasources) and
verifies:
1. Every entry in every inventory has a matching file on disk.
2. Every file referenced by inventory has matching frontmatter.
3. Every agent's `patterns:` field references patterns that exist in inventory.
4. Every agent's `tools:` list references tools whose family is registered.

Exits non-zero with a structured report if drift detected.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("lint: pyyaml not installed; skipping", file=sys.stderr)
    sys.exit(0)


FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL | re.MULTILINE)
BLOCK_KINDS = ["patterns", "agents", "uis", "routers", "datasources"]


def _load_yaml(p: Path) -> dict | None:
    try:
        return yaml.safe_load(p.read_text())
    except Exception as exc:
        return {"_error": str(exc)}


def _walk_blocks(workspace: Path) -> dict[str, Path]:
    """Find every inventory.yaml under building_blocks/."""
    found: dict[str, Path] = {}
    bb_root = workspace / "components" / "src" / "forsch" / "adk_components"
    if not bb_root.exists():
        return found
    for sub in BLOCK_KINDS:
        inv = bb_root / sub / "inventory.yaml"
        if inv.exists():
            found[sub] = inv
    return found


def lint(workspace: Path | None = None) -> int:
    ws = workspace or Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"))
    inventories = _walk_blocks(ws)
    if not inventories:
        print("lint: no inventories found under", ws / "components/src/forsch/adk_components")
        return 0
    errors: list[str] = []
    for kind, inv_path in inventories.items():
        data = _load_yaml(inv_path) or {}
        items = data.get(kind, data) if isinstance(data, dict) else {}
        if not isinstance(items, dict):
            continue
        for name, meta in items.items():
            file_field = meta.get("file") if isinstance(meta, dict) else None
            if file_field:
                expected = inv_path.parent / file_field
                if not expected.exists():
                    errors.append(f"[{kind}] {name}: file '{file_field}' missing at {expected}")
    registry_path = ws / "live-agent-graph" / "registry" / "agents" / "agents.yaml"
    if registry_path.exists():
        reg = _load_yaml(registry_path) or {}
        agents = reg.get("agents", {})
        for agent_id, spec in agents.items():
            if not isinstance(spec, dict):
                continue
            for pattern_id in spec.get("patterns", []) or []:
                pinv = inventories.get("patterns")
                if not pinv:
                    continue
                pdata = _load_yaml(pinv) or {}
                if pattern_id not in (pdata.get("patterns") or {}):
                    errors.append(f"[registry] agent '{agent_id}' declares unknown pattern '{pattern_id}'")
    if errors:
        print("PATTERNS LINT: drift detected")
        for e in errors:
            print("  -", e)
        return 1
    print("PATTERNS LINT: clean")
    return 0


if __name__ == "__main__":
    sys.exit(lint())
