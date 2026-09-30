"""Choosing Twilio or WhatsApp, and the WhatsApp request body.

The HTTP layer is stubbed at _request: what is under test is which endpoint is
chosen and what is sent to it, not ElevenLabs.
"""
import pytest

from app.core.config import get_settings
from app.integrations.elevenlabs.client import (
    WHATSAPP_OUTBOUND_CALL_PATH,
    ElevenLabsClient,
    ElevenLabsError,
    resolve_transport,
    whatsapp_user_id,
)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict]]:
    requests: list[tuple[str, str, dict]] = []

    def _fake(self, method, path, **kwargs):
        requests.append((method, path, kwargs.get("json") or {}))
        return {"success": True, "message": "ok", "conversation_id": "conv_1"}

    monkeypatch.setattr(ElevenLabsClient, "_request", _fake)
    return requests


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch):
    def _set(**values: str) -> None:
        settings = get_settings()
        base = {
            "elevenlabs_agent_id": "agent_1",
            "elevenlabs_phone_number_id": "phnum_twilio",
            "elevenlabs_twilio_agent_id": "",
            "elevenlabs_whatsapp_phone_number_id": "wa_phone_1",
            "whatsapp_call_permission_template_name": "call_permission_bn",
        }
        for key, value in {**base, **values}.items():
            monkeypatch.setattr(settings, key, value)

    return _set


def test_whatsapp_transport_calls_the_whatsapp_endpoint(sent, configure):
    configure(call_transport="whatsapp")
    ElevenLabsClient(api_key="k").place_call(
        to_number="+8801712345678", dynamic_variables={"patient_name": "Rahim"}
    )
    ((method, path, body),) = sent
    assert (method, path) == ("POST", WHATSAPP_OUTBOUND_CALL_PATH)
    assert body == {
        "agent_id": "agent_1",
        "whatsapp_phone_number_id": "wa_phone_1",
        "whatsapp_user_id": "8801712345678",
        "whatsapp_call_permission_request_template_name": "call_permission_bn",
        "whatsapp_call_permission_request_template_language_code": "bn",
        "conversation_initiation_client_data": {
            "dynamic_variables": {"patient_name": "Rahim"}
        },
    }


def test_twilio_transport_is_unchanged(sent, configure):
    configure(call_transport="twilio")
    ElevenLabsClient(api_key="k").place_call(
        to_number="+8801712345678", dynamic_variables={}
    )
    assert sent[0][1] == "/v1/convai/twilio/outbound-call"


def test_an_unknown_transport_is_refused_not_defaulted(sent, configure):
    configure(call_transport="whatsap")
    with pytest.raises(ElevenLabsError, match="not one of"):
        ElevenLabsClient(api_key="k").place_call(
            to_number="+8801712345678", dynamic_variables={}
        )
    assert sent == []


def test_a_missing_permission_template_is_a_named_error(sent, configure):
    configure(call_transport="whatsapp", whatsapp_call_permission_template_name="")
    with pytest.raises(Exception, match="WHATSAPP_CALL_PERMISSION_TEMPLATE_NAME"):
        ElevenLabsClient(api_key="k").place_call(
            to_number="+8801712345678", dynamic_variables={}
        )
    assert sent == []


@pytest.mark.parametrize("local", ["01712345678", "8801712345678", "+123"])
def test_whatsapp_ids_are_only_made_from_international_numbers(local):
    with pytest.raises(ElevenLabsError):
        whatsapp_user_id(local)


@pytest.mark.parametrize(
    ("number", "transport"),
    [
        ("+12125550100", "twilio"),  # New York
        ("+14165550134", "twilio"),  # Toronto
        ("+8801712345678", "whatsapp"),  # Bangladesh
        ("+447911123456", "whatsapp"),  # UK
        # "+1", but Jamaica and Puerto Rico: a prefix check would send these
        # over Twilio.
        ("+18765550100", "whatsapp"),
        ("+17875550100", "whatsapp"),
    ],
)
def test_auto_chooses_by_the_numbers_country(configure, number, transport):
    configure(call_transport="auto")
    assert resolve_transport(number) == transport


def test_twilio_regions_are_configurable(configure):
    configure(call_transport="auto", twilio_regions="us, ca, pr")
    assert resolve_transport("+17875550100") == "twilio"


@pytest.mark.parametrize("number", ["+15550100", "", "01712345678", None])
def test_auto_refuses_a_number_whose_country_it_cannot_tell(configure, number):
    configure(call_transport="auto")
    with pytest.raises(ElevenLabsError, match="cannot tell which country"):
        resolve_transport(number)


def test_a_fixed_transport_ignores_the_number(configure):
    configure(call_transport="whatsapp")
    assert resolve_transport("+12125550100") == "whatsapp"


def test_place_call_on_auto_dials_the_resolved_endpoint(sent, configure):
    configure(call_transport="auto")
    client = ElevenLabsClient(api_key="k")
    client.place_call(to_number="+12125550100", dynamic_variables={})
    client.place_call(to_number="+8801712345678", dynamic_variables={})
    assert [path for _, path, _ in sent] == [
        "/v1/convai/twilio/outbound-call",
        WHATSAPP_OUTBOUND_CALL_PATH,
    ]


def test_twilio_calls_use_the_twilio_agent_when_one_is_set(sent, configure):
    configure(call_transport="twilio", elevenlabs_twilio_agent_id="agent_en")
    ElevenLabsClient(api_key="k").place_call(
        to_number="+14165550134", dynamic_variables={}
    )
    assert sent[0][2]["agent_id"] == "agent_en"


def test_twilio_calls_fall_back_to_the_default_agent(sent, configure):
    configure(call_transport="twilio")
    ElevenLabsClient(api_key="k").place_call(
        to_number="+14165550134", dynamic_variables={}
    )
    assert sent[0][2]["agent_id"] == "agent_1"


def test_whatsapp_calls_never_use_the_twilio_agent(sent, configure):
    configure(call_transport="auto", elevenlabs_twilio_agent_id="agent_en")
    ElevenLabsClient(api_key="k").place_call(
        to_number="+8801712345678", dynamic_variables={}
    )
    assert sent[0][2]["agent_id"] == "agent_1"
