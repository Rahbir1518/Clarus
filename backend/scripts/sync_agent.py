#!/usr/bin/env python
"""Push an agent definition from version control to ElevenLabs.

    python scripts/sync_agent.py --dry-run
    python scripts/sync_agent.py
    python scripts/sync_agent.py --agent-id agent_abc123
    python scripts/sync_agent.py --spec agents/appointment_confirmation.yaml

The YAML file is the source of truth. Editing the agent in the ElevenLabs
dashboard works, but the next sync overwrites it — that is the point. The old
project lost its agent configuration because the dashboard was the only copy.

After a create, put the printed agent id into your .env as
ELEVENLABS_AGENT_ID so the call path can find it.
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

from app.integrations.elevenlabs.client import (  # noqa: E402
    ElevenLabsClient,
    ElevenLabsError,
)

DEFAULT_SPEC = Path(__file__).resolve().parent.parent / "agents" / "appointment_confirmation.yaml"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("ELEVENLABS_AGENT_ID", ""),
        help="Update this agent instead of creating a new one.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload that would be sent and exit.",
    )
    args = parser.parse_args()

    spec = load_spec(args.spec)
    wanted = declared_fields(spec)

    print(f"Spec:              {args.spec}")
    print(f"Agent name:        {spec.get('name')}")
    print(f"Data collection:   {', '.join(sorted(wanted)) or '(none)'}")

    if args.dry_run:
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
