"""ElevenLabs Agents API client.

Covers the two things Clarus needs: managing the agent definition (so it can
live in version control) and placing outbound calls.

API reference: https://elevenlabs.io/docs/eleven-agents/api-reference
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
import phonenumbers

from app.core.config import Settings, get_settings, require

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# The only Twilio-specific thing left in this module. ElevenLabs exposes one
# outbound endpoint per telephony provider; the rest of the call path — the
# agent, the dynamic variables, the post-call webhook — is identical whichever
# one is used. Moving to a SIP trunk (a licensed Bangladeshi IPTSP, say) is a
# change to this constant and nothing else.
OUTBOUND_CALL_PATH = "/v1/convai/twilio/outbound-call"
# SIP trunk: "/v1/convai/sip-trunk/outbound-call"

# WhatsApp is not a drop-in for the path above: its body names a WhatsApp
# phone number id, a recipient id and a permission template rather than an
# agent phone number. Hence its own method, and place_call() to choose.
# https://elevenlabs.io/docs/api-reference/whats-app/outbound-call
WHATSAPP_OUTBOUND_CALL_PATH = "/v1/convai/whatsapp/outbound-call"

TRANSPORTS = ("twilio", "whatsapp")

# The transport that dials nothing. A workflow's call_patient node parks the run
# and the call is answered from the browser over WebRTC instead — see
# routes/calls.py. Not in TRANSPORTS: those are the ones place_call can dial.
WEB_TRANSPORT = "web"

# Not a transport either: a rule for choosing one per call, by the country of
# the number being dialled. See resolve_transport.
AUTO_TRANSPORT = "auto"


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

    # -- agent tools --------------------------------------------------------
    #
    # Tools live in the workspace and agents reference them by id, so a sync
    # finds each by name and updates it in place rather than creating a new
    # copy every run. See scripts/sync_agent.py and agents/tools.yaml.

    def list_tools(self) -> list[dict]:
        tools: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["cursor"] = cursor
            result = self._request("GET", "/v1/convai/tools", params=params)
            tools.extend(result.get("tools", []))
            cursor = result.get("next_cursor")
            if not result.get("has_more") or not cursor:
                return tools

    def create_tool(self, tool_config: dict) -> str:
        result = self._request("POST", "/v1/convai/tools", json={"tool_config": tool_config})
        tool_id = result.get("id")
        if not tool_id:
            raise ElevenLabsError(f"Tool created but no id returned: {result}")
        return tool_id

    def update_tool(self, tool_id: str, tool_config: dict) -> None:
        self._request(
            "PATCH", f"/v1/convai/tools/{tool_id}", json={"tool_config": tool_config}
        )

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
        """Place an outbound call through the agent's bound phone number.

        Which carrier that number lives on is ElevenLabs' concern, not this
        module's — see OUTBOUND_CALL_PATH.

        Returns the raw response, which carries `conversation_id` and `callSid`
        when the call is successfully queued.
        """
        settings = get_settings()
        if not agent_id:
            # The Twilio agent if one is configured: a different language from
            # the WhatsApp one, since under CALL_TRANSPORT=auto Twilio carries
            # the US and Canada. See Settings.elevenlabs_twilio_agent_id.
            agent_id = settings.elevenlabs_twilio_agent_id
            if not agent_id:
                require("elevenlabs_agent_id")
                agent_id = settings.elevenlabs_agent_id
        if not agent_phone_number_id:
            require("elevenlabs_phone_number_id")
            agent_phone_number_id = settings.elevenlabs_phone_number_id

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

        result = self._request("POST", OUTBOUND_CALL_PATH, json=payload)
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

    def whatsapp_outbound_call(
        self,
        *,
        to_number: str,
        dynamic_variables: dict[str, Any],
        agent_id: str | None = None,
        whatsapp_phone_number_id: str | None = None,
        permission_template_name: str | None = None,
        permission_template_language: str | None = None,
    ) -> dict:
        """Call a patient on WhatsApp.

        WhatsApp requires the recipient's permission before a business may call
        them. ElevenLabs handles that: if permission is already granted the call
        is placed now; if not, it sends the permission-request template and
        dials **when the patient approves** — which may be hours later, and so
        outside the calling-hours window the workflow checked. For the pilot,
        have the patient grant permission first. `conversation_id` is null in
        that case; the call_patient node parks the run and flags it for review,
        and the webhook finds it again through its run reference (see
        webhook.py).
        """
        settings = get_settings()
        if agent_id is None:
            require("elevenlabs_agent_id")
            agent_id = settings.elevenlabs_agent_id
        if whatsapp_phone_number_id is None:
            require("elevenlabs_whatsapp_phone_number_id")
            whatsapp_phone_number_id = settings.elevenlabs_whatsapp_phone_number_id
        if permission_template_name is None:
            require("whatsapp_call_permission_template_name")
            permission_template_name = settings.whatsapp_call_permission_template_name
        permission_template_language = (
            permission_template_language
            or settings.whatsapp_call_permission_template_language
        )

        payload = {
            "agent_id": agent_id,
            "whatsapp_phone_number_id": whatsapp_phone_number_id,
            "whatsapp_user_id": whatsapp_user_id(to_number),
            "whatsapp_call_permission_request_template_name": permission_template_name,
            "whatsapp_call_permission_request_template_language_code": (
                permission_template_language
            ),
            "conversation_initiation_client_data": {
                "dynamic_variables": _stringify(dynamic_variables),
            },
        }

        result = self._request("POST", WHATSAPP_OUTBOUND_CALL_PATH, json=payload)
        if not result.get("success", False):
            raise ElevenLabsError(
                f"ElevenLabs declined the WhatsApp call: {result.get('message', result)}"
            )
        logger.info(
            "WhatsApp call queued: conversation_id=%s", result.get("conversation_id")
        )
        return result

    def place_call(
        self,
        *,
        to_number: str,
        dynamic_variables: dict[str, Any],
        transport: str | None = None,
    ) -> dict:
        """Place an outbound call over `transport`, or resolve_transport's choice.

        The one place that knows there is more than one. Callers get back a
        response carrying `conversation_id`, whichever was used. A caller that
        acts on the choice itself — the call_patient node, which treats a
        WhatsApp call differently — resolves it first and passes it in, so the
        transport it prepared for is the one that dials.
        """
        if transport is None:
            transport = resolve_transport(to_number)
        if transport == "whatsapp":
            return self.whatsapp_outbound_call(
                to_number=to_number, dynamic_variables=dynamic_variables
            )
        if transport == "twilio":
            return self.outbound_call(
                to_number=to_number, dynamic_variables=dynamic_variables
            )
        if transport == WEB_TRANSPORT:
            # The engine never gets here on this transport. Anything else that
            # does — scripts/test_call.py, say — is told why rather than being
            # given "not one of twilio, whatsapp" for a value that is valid.
            raise ElevenLabsError(
                "CALL_TRANSPORT=web places no outbound call; the call is "
                "answered in the browser. Use twilio or whatsapp to dial a number."
            )
        # Unknown is a refusal, not a default: a typo must not route a patient
        # call over a carrier nobody chose.
        raise ElevenLabsError(
            f"CALL_TRANSPORT={transport!r} is not one of "
            f"{', '.join((*TRANSPORTS, WEB_TRANSPORT, AUTO_TRANSPORT))}."
        )

    def conversation_token(self, agent_id: str | None = None) -> str:
        """Mint a short-lived token letting a browser open a WebRTC session.

        This exists so the API key never leaves the server. The key can spend
        money and read every conversation on the account; the token it returns
        is scoped to one agent and expires on its own.

        Shipping the API key to the browser instead would work, which is
        exactly why it needs saying: it would also publish it to anyone who
        opens devtools.
        """
        if agent_id is None:
            require("elevenlabs_agent_id")
            agent_id = get_settings().elevenlabs_agent_id

        result = self._request(
            "GET", "/v1/convai/conversation/token", params={"agent_id": agent_id}
        )
        token = result.get("token")
        if not token:
            raise ElevenLabsError(f"No token in the response: {result}")
        return token

    def get_conversation(self, conversation_id: str) -> dict:
        """Fetch a conversation, including transcript and analysis once done."""
        return self._request("GET", f"/v1/convai/conversations/{conversation_id}")


def resolve_transport(to_number: str | None, settings: Settings | None = None) -> str:
    """The transport that will carry a call to `to_number`.

    CALL_TRANSPORT itself, unless it is "auto": then Twilio for a number in one
    of TWILIO_REGIONS, WhatsApp for any other country.

    Chosen by the number, not by where a request came from. Every call here is
    outbound, and whoever starts one — a doctor pressing Run, a lab feed, the
    webhook resuming a run — is not the patient, so no request IP says where
    the patient is. The number does, and it is what the carrier has to reach.

    A number whose country cannot be determined is refused rather than sent
    down the WhatsApp branch as "some other country": that is the same guess
    about where a number lives that policy.assert_dialable refuses to make.
    """
    settings = settings or get_settings()
    configured = settings.call_transport_name
    if configured != AUTO_TRANSPORT:
        return configured
    region = phone_region(to_number or "")
    if region is None:
        raise ElevenLabsError(
            f"CALL_TRANSPORT=auto cannot tell which country {to_number!r} is "
            "in, so it cannot choose between Twilio and WhatsApp."
        )
    return "twilio" if region in settings.twilio_region_list else "whatsapp"


def phone_region(e164: str) -> str | None:
    """The ISO 3166 region of an international number ("US", "BD"), or None."""
    try:
        parsed = phonenumbers.parse(e164.strip(), None)
    except phonenumbers.NumberParseException:
        return None
    return phonenumbers.region_code_for_number(parsed)


def whatsapp_user_id(e164: str) -> str:
    """WhatsApp's recipient id: the E.164 number as digits, without the '+'.

    Only accepts international form. Stripping a local "017..." to digits would
    produce an id WhatsApp reads as some other country's number.
    """
    number = e164.strip()
    digits = "".join(ch for ch in number if ch.isdigit())
    if not number.startswith("+") or not 8 <= len(digits) <= 15:
        raise ElevenLabsError(
            f"{number!r} is not an international number (+<country><number>)."
        )
    return digits


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
