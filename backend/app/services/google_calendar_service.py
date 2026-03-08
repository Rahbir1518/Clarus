"""
Google Calendar Service
------------------------
Creates calendar events in the doctor's Google Calendar.

The doctor signs in via Auth0 with a Google social connection, so Auth0
stores the Google access & refresh tokens.  This service:

1. Calls the Auth0 Management API to retrieve the doctor's Google token.
2. Uses that token to call the Google Calendar REST API directly (via httpx).

Prerequisites
~~~~~~~~~~~~~
- Auth0 social connection for Google must be configured with the scopes:
    ``openid profile email https://www.googleapis.com/auth/calendar``
- The Auth0 Application (Machine‑to‑Machine) needs authorisation for the
  Management API with scopes ``read:users`` and ``read:user_idp_tokens``.
- ``AUTH0_DOMAIN``, ``AUTH0_CLIENT_ID``, ``AUTH0_CLIENT_SECRET`` must be set
  in ``.env``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auth0 Management API helpers
# ---------------------------------------------------------------------------

_mgmt_token_cache: dict[str, Any] = {}


async def _get_management_api_token() -> str:
    """
    Obtain an Auth0 Management API access token using client_credentials.
    Uses the M2M (Machine-to-Machine) app credentials.
    Caches the token until it expires.
    """
    import time

    cached = _mgmt_token_cache.get("token")
    if cached and _mgmt_token_cache.get("expires_at", 0) > time.time():
        return cached

    # Use M2M credentials; fall back to regular credentials for backwards compat
    client_id = settings.auth0_m2m_client_id or settings.auth0_client_id
    client_secret = settings.auth0_m2m_client_secret or settings.auth0_client_secret

    if not client_id or not client_secret:
        raise RuntimeError(
            "AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET must be set in .env. "
            "Create a Machine-to-Machine application in Auth0 and authorize it "
            "for the Management API with scopes: read:users, read:user_idp_tokens."
        )

    url = f"https://{settings.auth0_domain}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": f"https://{settings.auth0_domain}/api/v2/",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code >= 400:
        logger.error("Auth0 token error %s: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Failed to get Auth0 Management API token: {resp.text}")

    data = resp.json()
    _mgmt_token_cache["token"] = data["access_token"]
    _mgmt_token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    return data["access_token"]


async def _get_google_token_for_user(auth0_user_id: str) -> str:
    """
    Fetch the doctor's Google access_token from Auth0's identity store.

    ``auth0_user_id`` is the Auth0 ``user.sub`` value, e.g. ``google-oauth2|123…``.
    """
    mgmt_token = await _get_management_api_token()
    url = f"https://{settings.auth0_domain}/api/v2/users/{auth0_user_id}"
    headers = {"Authorization": f"Bearer {mgmt_token}"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code >= 400:
        logger.error("Auth0 get user error %s: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Failed to fetch user from Auth0: {resp.text}")

    user_data = resp.json()

    # Auth0 stores IdP tokens in the identities array
    for identity in user_data.get("identities", []):
        if identity.get("provider") == "google-oauth2":
            token = identity.get("access_token")
            if token:
                return token

    raise RuntimeError(
        f"No Google access_token found for Auth0 user {auth0_user_id}. "
        "Make sure the Google social connection is configured with calendar scopes."
    )


# ---------------------------------------------------------------------------
# Google Calendar API
# ---------------------------------------------------------------------------

GCAL_BASE = "https://www.googleapis.com/calendar/v3"


async def create_calendar_event(
    auth0_user_id: str,
    summary: str,
    start_iso: str,
    end_iso: str | None = None,
    description: str | None = None,
    timezone: str = "America/New_York",
    attendee_email: str | None = None,
) -> dict[str, Any]:
    """
    Create an event on the doctor's primary Google Calendar.

    Args:
        auth0_user_id: The doctor's Auth0 ``sub`` (e.g. ``google-oauth2|123``).
        summary: Event title (e.g. "Follow-up: John Doe").
        start_iso: ISO-8601 datetime for the event start.
        end_iso: ISO-8601 datetime for event end (defaults to start + 30 min).
        description: Optional event body text.
        timezone: IANA timezone string.
        attendee_email: Optional patient email to invite.

    Returns:
        The Google Calendar event resource (includes ``id``, ``htmlLink``).
    """
    google_token = await _get_google_token_for_user(auth0_user_id)

    # Default to 30-minute appointment if no end time
    if not end_iso:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = start_dt + timedelta(minutes=30)
        end_iso = end_dt.isoformat()

    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
    }
    if description:
        event_body["description"] = description
    if attendee_email:
        event_body["attendees"] = [{"email": attendee_email}]

    url = f"{GCAL_BASE}/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {google_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=event_body, headers=headers)

    if resp.status_code >= 400:
        logger.error("Google Calendar error %s: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Google Calendar API error {resp.status_code}: {resp.text}")

    event = resp.json()
    logger.info(
        "Google Calendar event created — id=%s link=%s",
        event.get("id"),
        event.get("htmlLink"),
    )
    return event
