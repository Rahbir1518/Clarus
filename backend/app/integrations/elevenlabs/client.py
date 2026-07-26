"""ElevenLabs Agents API client.

Covers the two things Clarus needs: managing the agent definition (so it can
live in version control) and placing outbound calls.

API reference: https://elevenlabs.io/docs/eleven-agents/api-reference
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings, require

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ElevenLabsError(RuntimeError):
    """An ElevenLabs API call failed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ElevenLabsClient:
    """Thin synchronous wrapper over the ElevenLabs REST API.

    Synchronous on purpose. Route handlers that use it are declared `def`, so
    FastAPI runs them in a threadpool and a blocking HTTP call costs a worker
    thread rather than stalling the event loop for every other request.
    """

    def __init__(self, api_key: str | None = None, *, base_url: str = BASE_URL) -> None:
        if api_key is None:
            require("elevenlabs_api_key")
            api_key = get_settings().elevenlabs_api_key
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    # -- plumbing -----------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self._base_url}{path}"
        headers = {"xi-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise ElevenLabsError(f"Could not reach ElevenLabs: {exc}") from exc

        if response.status_code >= 400:
            # Body first: ElevenLabs puts the useful reason in `detail`, and a
            # bare status code turns a five-second fix into a debugging session.
            raise ElevenLabsError(
                f"{method} {path} failed ({response.status_code}): {response.text[:500]}",
                status_code=response.status_code,
            )

        if not response.content:
            return {}
        return response.json()

    # -- agent definition ---------------------------------------------------

    def create_agent(self, definition: dict) -> str:
        """Create an agent and return its id."""
        result = self._request("POST", "/v1/convai/agents/create", json=definition)
        agent_id = result.get("agent_id")
        if not agent_id:
            raise ElevenLabsError(f"Agent created but no agent_id returned: {result}")
        return agent_id

    def update_agent(self, agent_id: str, definition: dict) -> dict:
        return self._request("PATCH", f"/v1/convai/agents/{agent_id}", json=definition)

    def get_agent(self, agent_id: str) -> dict:
        return self._request("GET", f"/v1/convai/agents/{agent_id}")

    def list_phone_numbers(self) -> list[dict]:
        result = self._request("GET", "/v1/convai/phone-numbers")
        if isinstance(result, list):
            return result
        return result.get("phone_numbers", [])

    # -- calling ------------------------------------------------------------

    def outbound_call(
        self,
        *,
        to_number: str,
        dynamic_variables: dict[str, Any],
        agent_id: str | None = None,
        agent_phone_number_id: str | None = None,
    ) -> dict:
        """Place an outbound call through the agent's Twilio number.

        Returns the raw response, which carries `conversation_id` and `callSid`
        when the call is successfully queued.
        """
        if agent_id is None or agent_phone_number_id is None:
            require("elevenlabs_agent_id", "elevenlabs_phone_number_id")
            settings = get_settings()
            agent_id = agent_id or settings.elevenlabs_agent_id
            agent_phone_number_id = (
                agent_phone_number_id or settings.elevenlabs_phone_number_id
            )

        payload = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "to_number": to_number,
            "conversation_initiation_client_data": {
                # Every {{placeholder}} in the agent prompt is substituted from
                # here. A name missing from this dict reaches the patient as a
                # literal "{{patient_name}}", so callers should use
                # build_dynamic_variables() rather than assembling it by hand.
                "dynamic_variables": _stringify(dynamic_variables),
            },
        }

        result = self._request(
            "POST", "/v1/convai/twilio/outbound-call", json=payload
        )
        if not result.get("success", False):
            raise ElevenLabsError(
                f"ElevenLabs declined the call: {result.get('message', result)}"
            )
        logger.info(
            "Outbound call queued: conversation_id=%s call_sid=%s",
            result.get("conversation_id"),
            result.get("callSid"),
        )
        return result

    def get_conversation(self, conversation_id: str) -> dict:
        """Fetch a conversation, including transcript and analysis once done."""
        return self._request("GET", f"/v1/convai/conversations/{conversation_id}")


def _stringify(variables: dict[str, Any]) -> dict[str, Any]:
    """Coerce dynamic variable values to types ElevenLabs accepts.

    Only strings, numbers and booleans are supported. Anything else (a date, a
    UUID, None) is rendered as a string, because the alternative is a 422 from
    the API or a literal "None" spoken to a patient.
    """
    out: dict[str, Any] = {}
    for key, value in variables.items():
        if value is None:
            out[key] = ""
        elif isinstance(value, (str, bool, int, float)):
            out[key] = value
        else:
            out[key] = str(value)
    return out
