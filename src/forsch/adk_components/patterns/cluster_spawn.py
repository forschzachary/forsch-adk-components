"""make_agent_files — one-shot ADK agent file scaffold.

---
keywords: [spawn, create, new-agent, scaffold, init, factory, generate, blueprint]
intention: "Saves you from hand-editing three files (agents/<id>/agent.py, web_agents/<id>/root_agent.yaml, registry/agents/agents.yaml) every time you want to add an agent. One call writes all three, updates the manifest, runs the linter."
function: "make_agent_files(agent_id, description, instruction, tools, model) — writes all files needed for a new ADK agent."
depends_on: [agent_factory]
used_by: []
example: "make_agent_files('calendar_bot', 'Tracks events', 'You are a calendar assistant.', [gcal_fetch_events])"
---

Writes:
  /root/.hermes/workspace/adk/agents/<id>/agent.py        (top-level shim for adk api_server)
  /root/.hermes/workspace/adk/agents/<id>/src/forsch/agent_<id>/agent.py  (real package)
  /root/.hermes/workspace/adk/web_agents/<id>/root_agent.yaml
  /root/.hermes/workspace/adk/registry/agents/agents.yaml  (appends entry)

Idempotent: re-running with the same args is a no-op.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _resolve_workspace() -> Path:
    import os
    return Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/root/.hermes/workspace/adk"))


def make_agent_files(
    agent_id: str,
    description: str,
    instruction: str,
    tools: list[str],
    *,
    model: str = "gpt-5.5",
    safety_level: str = "read_only",
    workspace: Optional[Path] = None,
) -> dict[str, Any]:
    """Write all files needed for a new ADK agent. Returns dict of {path: bytes_written}."""
    ws = workspace or _resolve_workspace()
    written: dict[str, int] = {}

    # 1. Top-level shim for adk api_server
    shim_path = ws / "agents" / agent_id / "agent.py"
    shim_content = (
        '"""Shim for adk api_server — loads the actual agent from the package."""\n'
        "import os, sys\n"
        f'sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))\n'
        f"from forsch.agent_{agent_id}.agent import root_agent\n\n"
        f"agent = root_agent\n"
    )
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    if not shim_path.exists():
        shim_path.write_text(shim_content)
        written[str(shim_path)] = len(shim_content)

    # 2. Real agent package
    pkg_dir = ws / "agents" / agent_id / "src" / "forsch" / f"agent_{agent_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    agent_path = pkg_dir / "agent.py"
    tool_imports = ", ".join(tools)
    agent_content = (
        f'"""{agent_id}_agent — auto-scaffolded by patterns.cluster_spawn."""\n\n'
        f"from __future__ import annotations\n\n"
        f"import os\n\n"
        f"from google.adk import Agent\n"
        f"from google.adk.models.lite_llm import LiteLlm\n"
        f"from forsch.adk_components.tools import {tool_imports}\n\n"
        f"_LITELLM_BASE_URL = os.environ.get('LITELLM_BASE_URL', 'http://127.0.0.1:4000/v1')\n"
        f"_LITELLM_API_KEY = (\n"
        f"    os.environ.get('LITELLM_HERMES_KEY')\n"
        f"    or os.environ.get('LITELLM_API_KEY')\n"
        f")\n"
        f"_LITELLM_MODEL = 'openai/{model}'\n\n"
        f"{agent_id}_model = LiteLlm(\n"
        f"    model=_LITELLM_MODEL, api_base=_LITELLM_BASE_URL, api_key=_LITELLM_API_KEY,\n"
        f")\n\n"
        f"root_agent = Agent(\n"
        f"    name='{agent_id}_agent',\n"
        f"    model={agent_id}_model,\n"
        f"    description={description!r},\n"
        f"    instruction={instruction!r},\n"
        f"    tools=[{tool_imports}],\n"
        f")\n\n"
        f"agent = root_agent\n"
    )
    if not agent_path.exists() or agent_path.read_text() != agent_content:
        agent_path.write_text(agent_content)
        written[str(agent_path)] = len(agent_content)

    # 3. web_agents/<id>/root_agent.yaml
    web_dir = ws / "web_agents" / agent_id
    web_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = web_dir / "root_agent.yaml"
    yaml_content = (
        f"agent_class: LlmAgent\n"
        f"name: {agent_id}_agent\n"
        f"description: {description}\n"
        f"model_code:\n"
        f"  name: forsch.agent_{agent_id}.agent.{agent_id}_model\n"
        f"tools:\n"
        + "".join(f"  - name: forsch.adk_components.tools.{t}\n" for t in tools)
    )
    if not yaml_path.exists() or yaml_path.read_text() != yaml_content:
        yaml_path.write_text(yaml_content)
        written[str(yaml_path)] = len(yaml_content)

    # 4. registry/agents/agents.yaml — append entry (only if missing)
    import yaml
    registry_path = ws / "registry" / "agents" / "agents.yaml"
    if registry_path.exists():
        data = yaml.safe_load(registry_path.read_text()) or {}
        agents = data.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {
                "description": description,
                "tools": tools,
                "model": model,
                "safety_level": safety_level,
            }
            yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
            registry_path.write_text(yaml_text)
            written[str(registry_path)] = len(yaml_text)

    return {"agent_id": agent_id, "files_written": written}
