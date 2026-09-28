#!/usr/bin/env python
"""Place a single test call. No database, no auth, no workflow engine.

This is the shortest path between "I have an ElevenLabs account" and "my phone
rang and the agent behaved correctly". Use it to iterate on the prompt in
agents/*.yaml before wiring anything else up.

    python scripts/test_call.py                        # calls CALL_ALLOWED_NUMBERS[0]
    python scripts/test_call.py --to +8801712345678
    python scripts/test_call.py --transport whatsapp   # override CALL_TRANSPORT
    python scripts/test_call.py --conversation conv_abc123   # fetch a result

IT PLACES A REAL CALL AND COSTS REAL MONEY. It only dials numbers listed in
CALL_ALLOWED_NUMBERS in backend/.env — put your own number there.

The workflow's other gates (kill switch, calling hours, attempt limit) are
skipped on purpose: this tests the agent, and CALLS_ENABLED stays false while
you do. The allowlist is the one gate it keeps, because a typo in --to would
otherwise ring a stranger.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import MissingConfiguration, get_settings  # noqa: E402
from app.engine.policy import ALLOWED_CALL_REASONS, normalise_phone  # noqa: E402
from app.integrations.elevenlabs.client import (  # noqa: E402
    TRANSPORTS,
    ElevenLabsClient,
    ElevenLabsError,
)
from app.integrations.elevenlabs.webhook import parse_post_call_payload  # noqa: E402


def build_dynamic_variables(args: argparse.Namespace) -> dict:
    """Every {{placeholder}} the agent prompt references.

    A name missing here is not an error at the API — it reaches the patient as
    the literal text "{{patient_name}}". Keep this in step with the spec.
    """
    return {
        "patient_name": args.patient_name,
        "doctor_name": args.doctor_name,
        "practice_name": args.practice_name,
        # The same fixed vocabulary the engine speaks from, in Bangla, so a
        # test call sounds like a real one.
        "appointment_reason": ALLOWED_CALL_REASONS[args.reason_code],
        "callback_number": args.callback_number
        or get_settings().practice_callback_number,
        "timezone": args.timezone,
        "today_date": date.today().isoformat(),
    }


def main() -> int:
    # Bangla on a Windows console: the default cp1252 encoding raises on the
    # first character it cannot represent.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        help="Destination in E.164, e.g. +8801712345678. Defaults to the first "
        "entry of CALL_ALLOWED_NUMBERS, and must be in that list.",
    )
    parser.add_argument(
        "--transport", choices=TRANSPORTS, help="Defaults to CALL_TRANSPORT."
    )
    parser.add_argument("--conversation", help="Fetch a finished conversation instead")
    parser.add_argument("--patient-name", default="Alex Kim")
    parser.add_argument("--doctor-name", default="Dr. Morgan Reyes")
    parser.add_argument("--practice-name", default="Clarus Family Health")
    parser.add_argument(
        "--reason-code", choices=sorted(ALLOWED_CALL_REASONS), default="annual_check_up"
    )
    parser.add_argument(
        "--callback-number", help="Defaults to PRACTICE_CALLBACK_NUMBER."
    )
    parser.add_argument("--timezone", default="Asia/Dhaka")
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--phone-number-id", default=None)
    parser.add_argument(
        "--list-numbers",
        action="store_true",
        help="Show the phone numbers on the account and exit.",
    )
    args = parser.parse_args()

    try:
        client = ElevenLabsClient()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        if args.list_numbers:
            numbers = client.list_phone_numbers()
            if not numbers:
                print("No phone numbers on this account.")
                print("Import your Twilio number under Agents -> Phone Numbers.")
                return 1
            for number in numbers:
                print(
                    f"{number.get('phone_number', '?'):<18} "
                    f"id={number.get('phone_number_id', '?')} "
                    f"label={number.get('label', '')}"
                )
            return 0

        if args.conversation:
            conversation = client.get_conversation(args.conversation)
            result = parse_post_call_payload({"data": conversation})
            print(json.dumps(conversation, indent=2)[:3000])
            print("\n--- parsed ---")
            print(f"outcome:           {result.call_outcome}")
            print(f"reached patient:   {result.reached_patient}")
            print(f"patient confirmed: {result.patient_confirmed}")
            print(f"date / time:       {result.confirmed_date} {result.confirmed_time}")
            print(f"notes:             {result.patient_availability_notes}")
            print(f"needs review:      {result.needs_human_review}")
            print(f"bookable:          {result.is_bookable}")
            return 0

        settings = get_settings()
        allowed = [normalise_phone(n) for n in settings.call_allowed_number_list]
        if not allowed:
            print(
                "ERROR: CALL_ALLOWED_NUMBERS in backend/.env is empty. Put your own "
                "number there (E.164, e.g. +8801712345678) and run this again.",
                file=sys.stderr,
            )
            return 2
        to = normalise_phone(args.to) if args.to else allowed[0]
        if to not in allowed:
            print(
                f"ERROR: {to} is not in CALL_ALLOWED_NUMBERS. This script only "
                "dials numbers you have listed there.",
                file=sys.stderr,
            )
            return 2
        transport = args.transport or settings.call_transport_name

        variables = build_dynamic_variables(args)
        print("Dynamic variables:")
        for key, value in variables.items():
            print(f"  {key:<20} {value}")

        print(f"\nCalling {to} over {transport} ...")
        if transport == "whatsapp":
            print(
                "(If you have not granted this business call permission on "
                "WhatsApp yet, you get a permission request message first; the "
                "call comes once you accept it.)"
            )
            response = client.whatsapp_outbound_call(
                to_number=to, dynamic_variables=variables, agent_id=args.agent_id
            )
        else:
            response = client.outbound_call(
                to_number=to,
                dynamic_variables=variables,
                agent_id=args.agent_id,
                agent_phone_number_id=args.phone_number_id,
            )
    except (ElevenLabsError, MissingConfiguration) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    conversation_id = response.get("conversation_id")
    print(f"\nQueued. conversation_id={conversation_id}")
    if not conversation_id:
        print("No conversation id yet: the call is waiting on WhatsApp call permission.")
        return 0
    print("\nAfter the call ends, read the result back with:")
    print(f"  python scripts/test_call.py --conversation {conversation_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
