"""Build the agent's webhook tools from agents/tools.yaml.

Pure: a spec, a public URL and a secret in, ElevenLabs tool configurations out.
scripts/sync_agent.py does the network part.

Two parameters are never the model's to fill, and the builder adds them rather
than trusting the YAML to remember:

  * `conversation_id` comes from the ElevenLabs system variable
    `system__conversation_id`. It decides whose calendar is read, so a model
    that could write it — or a caller who talked the model into writing it —
    could read another practice's.
  * The `X-Clarus-Tool-Secret` header, which the backend checks first.

The URL and secret come from configuration (PUBLIC_API_URL,
ELEVENLABS_TOOL_SECRET), never from the YAML, so nothing environment-specific or
secret is committed.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

TOOL_SECRET_HEADER = "X-Clarus-Tool-Secret"
CONVERSATION_ID_PARAM = "conversation_id"
CONVERSATION_ID_VARIABLE = "system__conversation_id"


class ToolSpecError(ValueError):
    """agents/tools.yaml, or the configuration it needs, is not usable."""


def build_tool_configs(spec: Any, *, public_api_url: str, secret: str) -> list[dict]:
    if not secret:
        raise ToolSpecError(
            "ELEVENLABS_TOOL_SECRET is not set. The backend refuses every tool call "
            "without it, so registering the tools would give the agent tools that "
            "always fail."
        )
    parsed = urlparse(public_api_url or "")
    if parsed.scheme != "https" or not parsed.netloc:
        raise ToolSpecError(
            f"PUBLIC_API_URL must be the backend's public https origin (the ngrok "
            f"URL in development); got {public_api_url!r}. ElevenLabs calls the "
            f"tools from its own servers, so localhost cannot work."
        )
    if not isinstance(spec, dict) or not isinstance(spec.get("tools"), list):
        raise ToolSpecError("tools.yaml must contain a `tools:` list")

    base = public_api_url.rstrip("/")
    configs = []
    for tool in spec["tools"]:
        name, path = tool.get("name"), tool.get("path")
        if not name or not isinstance(path, str) or not path.startswith("/"):
            raise ToolSpecError(f"tool needs a name and a path starting with '/': {tool!r}")
        parameters = dict(tool.get("parameters") or {})
        if CONVERSATION_ID_PARAM in parameters:
            raise ToolSpecError(
                f"{name}: {CONVERSATION_ID_PARAM} is added by the builder from "
                f"{CONVERSATION_ID_VARIABLE}; do not declare it"
            )
        properties = {
            key: {"type": value.get("type", "string"), "description": value["description"]}
            for key, value in parameters.items()
        }
        properties[CONVERSATION_ID_PARAM] = {
            "type": "string",
            "dynamic_variable": CONVERSATION_ID_VARIABLE,
        }
        configs.append(
            {
                "type": "webhook",
                "name": name,
                "description": tool["description"].strip(),
                "response_timeout_secs": int(tool.get("response_timeout_secs", 10)),
                "api_schema": {
                    "url": base + path,
                    "method": "POST",
                    "request_headers": {TOOL_SECRET_HEADER: secret},
                    "request_body_schema": {
                        "type": "object",
                        "properties": properties,
                        "required": [*(tool.get("required") or []), CONVERSATION_ID_PARAM],
                    },
                },
            }
        )
    return configs


def masked(configs: list[dict]) -> list[dict]:
    """A copy safe to print: the secret header replaced."""
    out = []
    for config in configs:
        copy = {**config, "api_schema": {**config["api_schema"]}}
        copy["api_schema"]["request_headers"] = {TOOL_SECRET_HEADER: "***"}
        out.append(copy)
    return out
