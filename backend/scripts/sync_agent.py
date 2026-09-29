#!/usr/bin/env python
"""Push an agent definition from version control to ElevenLabs.

    python scripts/sync_agent.py --dry-run
    python scripts/sync_agent.py
    python scripts/sync_agent.py --agent-id agent_abc123
    python scripts/sync_agent.py --create     # new agent even if one is configured
    python scripts/sync_agent.py --spec agents/appointment_confirmation.yaml

The YAML file is the source of truth. Editing the agent in the ElevenLabs
dashboard works, but the next sync overwrites it — that is the point. The old
project lost its agent configuration because the dashboard was the only copy.

After a create, put the printed agent id into your .env as
ELEVENLABS_AGENT_ID so the call path can find it.

A spec with `tools_file:` also registers the webhook tools that file declares
(agents/tools.yaml) — found by name and updated in place — and attaches them to
the agent. That needs PUBLIC_API_URL (where ElevenLabs will call them) and
ELEVENLABS_TOOL_SECRET in .env; the sync refuses to run without them rather than
registering tools that could never succeed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

# Allow running as `python scripts/sync_agent.py` from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.integrations.elevenlabs.client import (  # noqa: E402
    ElevenLabsClient,
    ElevenLabsError,
)
from app.integrations.elevenlabs.tools import (  # noqa: E402
    ToolSpecError,
    build_tool_configs,
    masked,
)

DEFAULT_SPEC = Path(__file__).resolve().parent.parent / "agents" / "appointment_confirmation.yaml"


def _configured_agent_id() -> str:
    try:
        return get_settings().elevenlabs_agent_id
    except Exception:  # noqa: BLE001 - a half-filled .env should not stop --dry-run
        return ""


def load_spec(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        spec = yaml.safe_load(handle)
    if not isinstance(spec, dict):
        raise SystemExit(f"{path} did not parse to a mapping")
    if "conversation_config" not in spec:
        raise SystemExit(f"{path} has no conversation_config block")
    return spec


def declared_fields(spec: dict) -> set[str]:
    return set(
        (spec.get("platform_settings", {}) or {}).get("data_collection", {}) or {}
    )


def collected_fields(agent: dict) -> set[str]:
    """Read the data collection identifiers back off a fetched agent.

    The API has moved this key before, so look in both places it has lived
    rather than reporting a false mismatch.
    """
    platform = agent.get("platform_settings", {}) or {}
    for container in (platform, agent):
        data_collection = container.get("data_collection")
        if isinstance(data_collection, dict):
            return set(data_collection)
        if isinstance(data_collection, list):
            return {
                item.get("identifier")
                for item in data_collection
                if isinstance(item, dict) and item.get("identifier")
            }
    return set()


def load_tool_configs(spec: dict, spec_path: Path) -> list[dict]:
    """The webhook tools this spec asks for, or [] when it names none.

    Pops `tools_file` from the spec: it is ours, not an ElevenLabs field.
    """
    tools_file = spec.pop("tools_file", None)
    if not tools_file:
        return []
    with (spec_path.parent / tools_file).open("r", encoding="utf-8") as handle:
        tools_spec = yaml.safe_load(handle)
    settings = get_settings()
    return build_tool_configs(
        tools_spec,
        public_api_url=settings.public_api_url,
        secret=settings.elevenlabs_tool_secret,
    )


def upsert_tools(client: ElevenLabsClient, configs: list[dict]) -> list[str]:
    """Create or update each tool by name; return their ids in order."""
    existing = {
        (tool.get("tool_config") or {}).get("name"): tool.get("id")
        for tool in client.list_tools()
    }
    ids = []
    for config in configs:
        tool_id = existing.get(config["name"])
        if tool_id:
            print(f"  updating tool {config['name']} ({tool_id})")
            client.update_tool(tool_id, config)
        else:
            tool_id = client.create_tool(config)
            print(f"  created tool {config['name']} ({tool_id})")
        ids.append(tool_id)
    return ids


def main() -> int:
    # Bangla on a Windows console: the default cp1252 encoding raises on the
    # first character it cannot represent.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument(
        "--agent-id",
        # From the settings, not os.environ: backend/.env is read by
        # pydantic-settings and never reaches the process environment, so
        # os.environ alone missed it and every run created a new agent.
        default=os.environ.get("ELEVENLABS_AGENT_ID") or _configured_agent_id(),
        help="Update this agent instead of creating a new one. Defaults to "
        "ELEVENLABS_AGENT_ID.",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new agent even though ELEVENLABS_AGENT_ID is set.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload that would be sent and exit.",
    )
    args = parser.parse_args()
    if args.create:
        args.agent_id = ""

    spec = load_spec(args.spec)
    wanted = declared_fields(spec)
    try:
        tool_configs = load_tool_configs(spec, args.spec)
    except (OSError, ToolSpecError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Spec:              {args.spec}")
    print(f"Agent name:        {spec.get('name')}")
    print(f"Data collection:   {', '.join(sorted(wanted)) or '(none)'}")
    print(f"Tools:             {', '.join(c['name'] for c in tool_configs) or '(none)'}")
    for config in tool_configs:
        print(f"                   {config['name']} -> {config['api_schema']['url']}")

    if args.dry_run:
        if tool_configs:
            print("\n--- tools ---")
            print(json.dumps(masked(tool_configs), indent=2))
        print("\n--- payload ---")
        print(json.dumps(spec, indent=2)[:4000])
        print("\nDry run: nothing was sent.")
        return 0

    try:
        client = ElevenLabsClient()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("Set ELEVENLABS_API_KEY in your environment or .env", file=sys.stderr)
        return 2

    try:
        tool_ids: list[str] = []
        if tool_configs:
            print("\nSyncing tools ...")
            tool_ids = upsert_tools(client, tool_configs)
            # Tools are referenced by id; inline definitions are deprecated.
            spec["conversation_config"]["agent"]["prompt"]["tool_ids"] = tool_ids

        if args.agent_id:
            print(f"\nUpdating agent {args.agent_id} ...")
            client.update_agent(args.agent_id, spec)
            agent_id = args.agent_id
        else:
            print("\nCreating a new agent ...")
            agent_id = client.create_agent(spec)
            print(f"Created: {agent_id}")

        # Read back rather than trusting the write. A 200 only means the request
        # was accepted; if the data collection block landed under a key the API
        # does not read, the agent runs happily and collects nothing — which is
        # precisely how the previous system ended up regex-scraping transcripts.
        print("Verifying ...")
        agent = client.get_agent(agent_id)
    except ElevenLabsError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    actual = collected_fields(agent)
    missing = wanted - actual

    attached = set(
        ((agent.get("conversation_config") or {}).get("agent") or {})
        .get("prompt", {})
        .get("tool_ids")
        or []
    )
    if set(tool_ids) - attached:
        print(
            f"\nWARNING: tools {sorted(set(tool_ids) - attached)} were synced but "
            f"are not attached to the agent. It will not be able to check the "
            f"calendar during calls.",
            file=sys.stderr,
        )
        return 1
    if tool_ids:
        print(f"Tools attached:    {len(tool_ids)}")

    print(f"\nAgent id:          {agent_id}")
    print(f"Fields on server:  {', '.join(sorted(actual)) or '(none)'}")

    if missing:
        print(
            f"\nWARNING: these fields are in the spec but not on the server: "
            f"{', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        print(
            "The agent will run but will not collect them, so every call will "
            "come back needing human review. Check the data collection section "
            "in the ElevenLabs dashboard against the spec before calling any "
            "real patient.",
            file=sys.stderr,
        )
        return 1

    print("\nAll declared fields are present on the server.")
    print(f"\nAdd to your .env:\n  ELEVENLABS_AGENT_ID={agent_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
