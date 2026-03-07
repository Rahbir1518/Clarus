# Implementation Plan: Lab Results → ElevenLabs Call → Google Calendar Appointment

## Overview

Wire up the full end-to-end workflow: lab results arrive → workflow engine triggers ElevenLabs Conversational AI to call the patient via Twilio → patient schedules an appointment during the call → appointment is created in the doctor's Google Calendar.

---

## Architecture

```
Lab event hits POST /api/lab-event
  → workflow_engine finds matching ENABLED workflow
  → BFS walks nodes:
      1. Trigger: lab_results_received ✓ (already works)
      2. Condition: check_result_values ✓ (already works)
      3. Action: call_patient → NEW: ElevenLabs Conversational AI outbound call via Twilio
      4. Action: schedule_appointment → NEW: Google Calendar event creation
      5. Output: send_summary_to_doctor → NEW: notification/log
```

---

## Changes

### 1. Backend config (`app/core/config.py`)
Add new env vars:
- `elevenlabs_api_key` — ElevenLabs API key
- `elevenlabs_agent_id` — The agent ID from ElevenLabs dashboard
- `auth0_domain`, `auth0_client_id`, `auth0_client_secret` — Already in `.env`, just not in Settings

### 2. New service: `app/services/elevenlabs_service.py`
ElevenLabs Conversational AI integration:
- `initiate_call(phone, agent_id, metadata)` — Uses ElevenLabs Conversational AI API to start an outbound call to the patient via Twilio. The ElevenLabs agent handles the full conversation (informing about lab results, scheduling appointment).
- ElevenLabs manages the Twilio connection — we just tell ElevenLabs to call a phone number with the agent.
- Pass dynamic context (patient name, lab result details, available time slots) to the agent via `conversation_config_override` or `dynamic_variables`.

### 3. New service: `app/services/google_calendar_service.py`
Google Calendar integration using Auth0's Google tokens:
- `get_google_token_from_auth0(user_id)` — Calls Auth0 Management API to fetch the doctor's Google access/refresh token (stored by Auth0 when the doctor logged in via Google).
- `create_appointment(google_token, patient_name, datetime_start, datetime_end, summary)` — Creates a Google Calendar event using the Google Calendar API.
- Uses `httpx` (already in requirements) — no need for the full `google-api-python-client` package.

### 4. Update workflow engine (`app/services/workflow_engine.py`)
- Replace `_handle_call_patient` — Instead of raw Twilio TwiML, call ElevenLabs Conversational AI API to initiate an outbound call. ElevenLabs handles the Twilio connection internally.
- Implement `_handle_schedule_appointment` — Call Google Calendar service to create an event. The appointment details (time, duration) come from the workflow node's `data.params` or from the ElevenLabs call outcome (stored in call_log).
- Wire both handlers into `_ACTION_HANDLERS` dispatch table.

### 5. Update endpoints (`app/api/endpoints.py`)
- Add `POST /api/elevenlabs/webhook` — Webhook endpoint that ElevenLabs calls after a conversation ends. Receives call outcome (appointment time agreed, patient response, transcript). Updates the call_log and triggers the next workflow step (schedule_appointment).
- Update Twilio voice/gather webhooks to coexist with ElevenLabs (ElevenLabs manages its own Twilio connection, so the existing webhooks remain as fallback).

### 6. Update `.env.example` and `config.py`
Add all new environment variables.

### 7. Update `requirements.txt`
Add `PyJWT` and `cryptography` (for Auth0 Management API token if needed — actually PyJWT is already there). May need `google-auth` for calendar API convenience, but can use raw httpx.

---

## ElevenLabs Conversational AI Call Flow

1. Workflow engine hits `call_patient` node
2. Backend calls ElevenLabs API: `POST https://api.elevenlabs.io/v1/convai/conversations/create-phone-call`
   - Body: `{ agent_id, phone_number (patient), dynamic_variables: { patient_name, lab_results, doctor_name } }`
3. ElevenLabs connects to Twilio and calls the patient
4. ElevenLabs agent has the conversation (already configured in their dashboard with system prompt)
5. When call ends, ElevenLabs sends data to our webhook `POST /api/elevenlabs/webhook`
6. Webhook receives: conversation transcript, extracted data (appointment time, patient responses)
7. Backend updates call_log with outcome, then triggers `schedule_appointment` if the patient agreed

## Google Calendar Flow

1. `schedule_appointment` node is reached in workflow
2. Backend needs the doctor's Google access token
3. Call Auth0 Management API: `GET /api/v2/users/{doctor_auth0_id}` → response includes `identities[0].access_token` (the Google OAuth token)
4. Use that token to call Google Calendar API: `POST https://www.googleapis.com/calendar/v3/calendars/primary/events`
5. Create the calendar event with patient name, appointment time, etc.

## Auth0 Management API Access

To read the doctor's Google token from Auth0, we need a Management API token:
- Use client_credentials grant: `POST https://{domain}/oauth/token` with `client_id`, `client_secret`, `audience: https://{domain}/api/v2/`, `grant_type: client_credentials`
- This returns a Management API access token
- Then call `GET /api/v2/users/{user_id}` to get the identity provider tokens

**Prerequisite**: The Auth0 application must have "Auth0 Management API" authorized with `read:users` and `read:user_idp_tokens` scopes. The Google social connection in Auth0 must be configured with Calendar API scopes.

---

## Files to create/modify

| File | Action |
|---|---|
| `backend/app/core/config.py` | Modify — add ElevenLabs + Auth0 env vars |
| `backend/app/services/elevenlabs_service.py` | Create — ElevenLabs Conversational AI integration |
| `backend/app/services/google_calendar_service.py` | Create — Google Calendar via Auth0 Google tokens |
| `backend/app/services/workflow_engine.py` | Modify — wire real handlers for call_patient + schedule_appointment |
| `backend/app/api/endpoints.py` | Modify — add ElevenLabs webhook endpoint |
| `backend/.env.example` | Modify — add new env vars |
| `backend/requirements.txt` | Modify — if any new deps needed |
