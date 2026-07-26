#!/usr/bin/env python
"""Place a single test call. No database, no auth, no workflow engine.

This is the shortest path between "I have an ElevenLabs account" and "my phone
rang and the agent behaved correctly". Use it to iterate on the prompt in
agents/*.yaml before wiring anything else up.

    python scripts/test_call.py --to +15551234567
    python scripts/test_call.py --to +15551234567 --patient-name "Alex Kim"
    python scripts/test_call.py --conversation conv_abc123   # fetch a result

IT PLACES A REAL PHONE CALL AND COSTS REAL MONEY. Point it at your own phone.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations.elevenlabs.client import (  # noqa: E402
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
        "appointment_reason": args.reason,
        "callback_number": args.callback_number,
        "timezone": args.timezone,
        "today_date": date.today().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", help="Destination number in E.164, e.g. +15551234567")
    parser.add_argument("--conversation", help="Fetch a finished conversation instead")
    parser.add_argument("--patient-name", default="Alex Kim")
    parser.add_argument("--doctor-name", default="Dr. Morgan Reyes")
    parser.add_argument("--practice-name", default="Clarus Family Health")
    parser.add_argument("--reason", default="your annual check-up")
    parser.add_argument("--callback-number", default="+15550000000")
    parser.add_argument("--timezone", default="America/Toronto")
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

        if not args.to:
            parser.error("one of --to, --conversation or --list-numbers is required")

        variables = build_dynamic_variables(args)
        print("Dynamic variables:")
        for key, value in variables.items():
            print(f"  {key:<20} {value}")

        print(f"\nCalling {args.to} ...")
        response = client.outbound_call(
            to_number=args.to,
            dynamic_variables=variables,
            agent_id=args.agent_id,
            agent_phone_number_id=args.phone_number_id,
        )
    except ElevenLabsError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    conversation_id = response.get("conversation_id")
    print(f"\nQueued. conversation_id={conversation_id} call_sid={response.get('callSid')}")
    print("\nAfter the call ends, read the result back with:")
    print(f"  python scripts/test_call.py --conversation {conversation_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
