"""
ElevenLabs Conversational AI Service
-------------------------------------
Initiates outbound phone calls using ElevenLabs' Conversational AI
connected to Twilio.  ElevenLabs manages the full voice conversation
(informing the patient about lab results, scheduling an appointment, etc.).

After the call ends, results can be fetched via polling (GET conversation)
or received via webhook at ``POST /api/elevenlabs/webhook``.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


async def initiate_outbound_call(
    patient_phone: str,
    patient_name: str,
    doctor_name: str,
    lab_result_summary: str | None = None,
    facility_name: str | None = None,
    facility_address: str | None = None,
    facility_phone_number: str | None = None,
    call_reason: str | None = None,
    available_slots: str | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start an ElevenLabs Conversational AI outbound call to *patient_phone*.

    The ElevenLabs agent (configured in their dashboard) handles the entire
    conversation.  We inject dynamic context about the patient and lab
    results so the agent can reference them during the call.

    Prerequisites:
      - An ElevenLabs agent created in the dashboard (ELEVENLABS_AGENT_ID)
      - A phone number imported into ElevenLabs (Twilio integration) which
        gives you an ELEVENLABS_PHONE_NUMBER_ID
      - ELEVENLABS_API_KEY set in .env

    Returns the ElevenLabs API response (includes ``conversation_id``).
    """
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")
    if not settings.elevenlabs_agent_id:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not configured")
    if not settings.elevenlabs_phone_number_id:
        raise RuntimeError(
            "ELEVENLABS_PHONE_NUMBER_ID is not configured. "
            "Import your Twilio phone number in the ElevenLabs dashboard "
            "(Phone Numbers section) to get this ID."
        )

    # ----- build dynamic variables that the agent prompt can reference -----
    dynamic_variables = {
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "lab_result_summary": lab_result_summary or "recent lab results",
        "facility_name": facility_name or "Credit Valley Medical Centre",
        "facility_address": facility_address or "",
        "facility_phone_number": facility_phone_number or "",
        "call_reason": call_reason or "recent lab results",
        "available_slots": available_slots or "Monday at 10:00 AM, Wednesday at 2:00 PM, or Friday at 9:00 AM",
        **(extra_context or {}),
    }

    # ----- build the request payload -----
    # Docs: POST /v1/convai/twilio/outbound-call
    # Required: agent_id, agent_phone_number_id, to_number
    payload: dict[str, Any] = {
        "agent_id": settings.elevenlabs_agent_id,
        "agent_phone_number_id": settings.elevenlabs_phone_number_id,
        "to_number": patient_phone,
        "conversation_initiation_client_data": {
            "dynamic_variables": dynamic_variables,
        },
    }

    url = f"{ELEVENLABS_BASE}/convai/twilio/outbound-call"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        body = resp.text
        logger.error("ElevenLabs API error %s: %s", resp.status_code, body)
        raise RuntimeError(f"ElevenLabs API error {resp.status_code}: {body}")

    data = resp.json()
    logger.info(
        "ElevenLabs call initiated — conversation_id=%s, callSid=%s",
        data.get("conversation_id"),
        data.get("callSid"),
    )
    return data


async def get_conversation(conversation_id: str) -> dict[str, Any]:
    """Fetch conversation details (transcript, analysis) from ElevenLabs."""
    url = f"{ELEVENLABS_BASE}/convai/conversations/{conversation_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code >= 400:
        logger.error("ElevenLabs GET conversation error: %s", resp.text)
        raise RuntimeError(f"ElevenLabs error {resp.status_code}: {resp.text}")

    return resp.json()
