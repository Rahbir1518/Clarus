"""The tool definitions pushed to ElevenLabs, built from agents/tools.yaml."""
from pathlib import Path

import pytest
import yaml

from app.integrations.elevenlabs.tools import (
    CONVERSATION_ID_VARIABLE,
    TOOL_SECRET_HEADER,
    ToolSpecError,
    build_tool_configs,
    masked,
)
from app.main import app

AGENTS = Path(__file__).resolve().parent.parent / "agents"
URL = "https://example.ngrok-free.dev"


def _spec() -> dict:
    return yaml.safe_load((AGENTS / "tools.yaml").read_text(encoding="utf-8"))


def _configs() -> list[dict]:
    return build_tool_configs(_spec(), public_api_url=URL + "/", secret="s3cret")


def test_every_tool_points_at_a_route_that_exists():
    routes = set(app.openapi()["paths"])
    for config in _configs():
        url = config["api_schema"]["url"]
        assert url.startswith(URL + "/api/")
        assert url.removeprefix(URL) in routes


def test_the_conversation_id_is_never_the_models_to_fill():
    """It decides whose calendar is read."""
    for config in _configs():
        prop = config["api_schema"]["request_body_schema"]["properties"]["conversation_id"]
        assert prop == {"type": "string", "dynamic_variable": CONVERSATION_ID_VARIABLE}
        assert "conversation_id" in config["api_schema"]["request_body_schema"]["required"]


def test_a_spec_declaring_its_own_conversation_id_is_refused():
    spec = _spec()
    spec["tools"][0]["parameters"]["conversation_id"] = {"description": "the id"}
    with pytest.raises(ToolSpecError):
        build_tool_configs(spec, public_api_url=URL, secret="s3cret")


def test_every_tool_sends_the_secret_and_printing_hides_it():
    configs = _configs()
    assert all(c["api_schema"]["request_headers"] == {TOOL_SECRET_HEADER: "s3cret"} for c in configs)
    assert "s3cret" not in str(masked(configs))
    # masked() is a copy; the real configs still carry the secret.
    assert configs[0]["api_schema"]["request_headers"][TOOL_SECRET_HEADER] == "s3cret"


@pytest.mark.parametrize("url", ["", "http://localhost:8000", "localhost", "ftp://x.dev"])
def test_a_url_elevenlabs_cannot_reach_is_refused(url):
    with pytest.raises(ToolSpecError):
        build_tool_configs(_spec(), public_api_url=url, secret="s3cret")


def test_no_secret_means_no_tools():
    with pytest.raises(ToolSpecError):
        build_tool_configs(_spec(), public_api_url=URL, secret="")


@pytest.mark.parametrize("spec", ["appointment_confirmation.yaml", "appointment_confirmation_bn.yaml"])
def test_both_agents_use_the_tools_they_are_told_about(spec):
    """The prompt names each tool; a renamed tool would leave the agent calling nothing."""
    text = (AGENTS / spec).read_text(encoding="utf-8")
    assert yaml.safe_load(text)["tools_file"] == "tools.yaml"
    for tool in _spec()["tools"]:
        assert tool["name"] in text
