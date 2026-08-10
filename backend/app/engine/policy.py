"""AI_CALL_SAFETY_POLICY.md, as code.

Read that document first. This module is its enforcement, and the two are meant
to be checkable against each other — every **enforced** claim there is a
function here, and every function here exists because of a paragraph there.

Everything raises `PolicyRefusal`, which the engine records as a `blocked` step
and which halts the branch. Nothing here returns a boolean that a caller could
forget to check, and nothing here silently modifies what it was given: the one
design rule in this module is that a refusal is loud. A gate that quietly
sanitises its input leaves the workflow's author believing something happened
that did not.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import Settings, get_settings


class PolicyRefusal(Exception):
    """A safety rule refuses this action.

    Carries a message written for whoever drew the workflow, since they are the
    person who has to change something. It goes into the execution log verbatim.
    """


# ---------------------------------------------------------------------------
# What may be said to a patient
# ---------------------------------------------------------------------------

# The entire vocabulary of reasons a patient may be given for the call. A
# `call_patient` node carries a reason_code, not a sentence, and this dict is
# why: there is no free-text path from a workflow parameter to a patient's ear.
#
# The previous design had `lab_result_summary` — author-written clinical text
# interpolated into the agent prompt. Removing that parameter is not enough on
# its own, because the next person to want a personalised call would add
# another one. A fixed vocabulary makes the absence structural.
#
# Phrases are written to be spoken, and they are in Bangla: `DEFAULT_TIMEZONE`
# is Asia/Dhaka and the calls this places are to patients in Bangladesh. They
# complete "I'm calling about ..." in the agent's own words.
#
# Note that `agents/appointment_confirmation.yaml` still declares `language: en`
# with an English prompt, so today a Bangla reason is spoken inside an otherwise
# English call. That is the arrangement the call-test page already had; it is not
# a good end state, and localising the agent definition is its own change.
#
# Adding a second language means giving each code another phrase and choosing
# between them — not reopening the free-text path this dict exists to close.
ALLOWED_CALL_REASONS: Final[dict[str, str]] = {
    "results_ready": "আপনার সাম্প্রতিক পরীক্ষার ফলাফল, যা নিয়ে আলোচনা করা প্রয়োজন",
    "follow_up": "একটি ফলো-আপ অ্যাপয়েন্টমেন্ট",
    "annual_check_up": "আপনার নিয়মিত স্বাস্থ্য পরীক্ষা",
    "medication_review": "আপনার ওষুধের পর্যালোচনা",
    "appointment_confirmation": "আমরা আপনার জন্য যে অ্যাপয়েন্টমেন্টটি নির্ধারণ করেছি",
    "missed_appointment": "একটি অ্যাপয়েন্টমেন্ট যা মিস হয়ে গেছে",
}

DEFAULT_REASON_CODE: Final[str] = "results_ready"

# Parameter names that mean somebody is trying to put clinical content into a
# call. Presence with a non-empty value is refused outright — see the policy
# document on why the value is not simply dropped.
#
# A denylist, which is normally the weaker choice, and here it is doing a
# different job than usual: the allowlist is ALLOWED_CALL_REASONS above, and it
# is total, because reason_code is the only parameter the call path reads. This
# list exists to give a recognisable error to a graph saved before the policy —
# a graph carrying lab_result_summary would otherwise execute with the field
# harmlessly ignored, and its author would never learn the summary they wrote
# was never spoken.
CLINICAL_PARAM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "lab_result_summary",
        "result_summary",
        "results",
        "lab_values",
        "diagnosis",
        "test_result",
        "test_results",
        "clinical_notes",
        "clinical_summary",
        "interpretation",
    }
)


def resolve_call_reason(params: dict[str, str]) -> str:
    """The phrase to speak, or a refusal.

    An absent reason_code falls back to the default; an unrecognised one does
    not. The difference is that an absent value is a graph drawn before the
    parameter existed, while an unrecognised value is somebody's intent that we
    cannot honour — most likely a typo, and defaulting a typo means a patient is
    told something other than what the author chose.
    """
    code = (params.get("reason_code") or "").strip() or DEFAULT_REASON_CODE
    phrase = ALLOWED_CALL_REASONS.get(code)
    if phrase is None:
        allowed = ", ".join(sorted(ALLOWED_CALL_REASONS))
        raise PolicyRefusal(
            f"reason_code {code!r} is not one this system will say to a patient. "
            f"Allowed: {allowed}"
        )
    return phrase


def assert_no_clinical_params(params: dict[str, str]) -> None:
    """Refuse a call node carrying clinical content.

    Empty values pass: the builder writes every declared parameter, including
    ones left blank, so an empty `lab_result_summary` is a graph that has the
    field but does not use it.
    """
    offending = sorted(
        name
        for name in CLINICAL_PARAM_NAMES
        if (params.get(name) or "").strip()
    )
    if offending:
        raise PolicyRefusal(
            "This call carries clinical content in "
            + ", ".join(offending)
            + ". The voice agent never discloses clinical results — see "
            "AI_CALL_SAFETY_POLICY.md. Remove the parameter and use a "
            "reason_code, or route this branch to a human."
        )


def assert_not_abnormal(*, abnormal: bool, reason: str) -> None:
    """Refuse a call on a run that is carrying an abnormal result.

    `reason` is how the run became tainted, so the log says which of the three
    routes it was rather than just that it happened.
    """
    if abnormal:
        raise PolicyRefusal(
            f"This run is on an abnormal-result path ({reason}), which routes to "
            f"a human rather than to an automated call."
        )


# ---------------------------------------------------------------------------
# Whether to dial at all
# ---------------------------------------------------------------------------

_NON_DIALLABLE = re.compile(r"[^\d+]")


def normalise_phone(raw: Any) -> str:
    """Reduce a phone number to `+` and digits.

    `patients.phone` is free text, so "(416) 555-0134" and "+1 416 555 0134" are
    both things the database holds. A leading "00" is rewritten to "+", which is
    the same international prefix dialled the older way.
    """
    text = _NON_DIALLABLE.sub("", str(raw or ""))
    # A "+" anywhere but the front is meaningless; keep only a leading one.
    lead = "+" if text.startswith("+") else ""
    digits = text.replace("+", "")
    if not lead and digits.startswith("00"):
        return "+" + digits[2:]
    return lead + digits


def assert_dialable(phone: str) -> str:
    """Require an E.164 number, and return it normalised.

    Refused here rather than left to the provider. A local-format number is not
    a number this system knows how to dial — the country is missing, and which
    country to assume is precisely the guess that puts a call through to a
    stranger who happens to hold that number somewhere else.
    """
    normalised = normalise_phone(phone)
    if not normalised.startswith("+"):
        raise PolicyRefusal(
            f"Patient phone number is not in international form. Got "
            f"{normalised or '(empty)'}; needs a country code, e.g. +8801712345678."
        )
    if len(normalised) < 8:
        raise PolicyRefusal(
            f"Patient phone number {normalised!r} is too short to be dialled."
        )
    return normalised


def assert_calls_enabled(settings: Settings | None = None) -> None:
    """The kill switch. Defaults closed."""
    settings = settings or get_settings()
    if not settings.calls_enabled:
        raise PolicyRefusal(
            "Outbound calls are switched off for this deployment "
            "(CALLS_ENABLED is false). The run stopped before dialling."
        )


def assert_number_allowed(phone: str, settings: Settings | None = None) -> None:
    """The stage-1 allowlist: only these numbers may be dialled.

    An empty allowlist while enforcement is on means nothing is callable, and
    that is the intended reading. Lifting the restriction is
    CALL_ALLOWLIST_ENFORCED=false — a sentence somebody has to write, rather
    than something a forgotten variable achieves.
    """
    settings = settings or get_settings()
    if not settings.call_allowlist_enforced:
        return

    allowed = {normalise_phone(n) for n in settings.call_allowed_number_list}
    if not allowed:
        raise PolicyRefusal(
            "The outbound call allowlist is empty, so no number is callable. "
            "Add your own number to CALL_ALLOWED_NUMBERS to place test calls."
        )
    if normalise_phone(phone) not in allowed:
        raise PolicyRefusal(
            f"{normalise_phone(phone)} is not on the outbound call allowlist. "
            f"Development may only call numbers listed in CALL_ALLOWED_NUMBERS."
        )


def calling_zone(settings: Settings | None = None) -> ZoneInfo:
    """The timezone calling hours are measured in.

    One zone for everybody, which is a known gap recorded in the policy
    document. A zone name the platform cannot resolve is a refusal rather than a
    fallback to UTC: silently measuring a patient's evening in the wrong zone is
    how a call lands at three in the morning.
    """
    settings = settings or get_settings()
    try:
        return ZoneInfo(settings.default_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise PolicyRefusal(
            f"Cannot resolve DEFAULT_TIMEZONE {settings.default_timezone!r}, so "
            f"the calling-hours window cannot be checked: {exc}"
        ) from exc


def assert_within_calling_hours(
    now: datetime | None = None, settings: Settings | None = None
) -> None:
    """Refuse a call outside the local calling window.

    Start inclusive, end exclusive. A window that does not describe a forward
    span of hours is a misconfiguration, and it refuses rather than wrapping
    around midnight — a wrap would turn a transposed pair of numbers into
    permission to call all night.
    """
    settings = settings or get_settings()
    start, end = settings.calling_hours_start, settings.calling_hours_end
    if not 0 <= start < end <= 24:
        raise PolicyRefusal(
            f"Calling hours {start}–{end} are not a valid window; expected "
            f"0 <= CALLING_HOURS_START < CALLING_HOURS_END <= 24."
        )

    zone = calling_zone(settings)
    local = (now or datetime.now(zone)).astimezone(zone)
    if not start <= local.hour < end:
        raise PolicyRefusal(
            f"It is {local.strftime('%H:%M')} in {settings.default_timezone}, "
            f"outside the {start:02d}:00–{end:02d}:00 calling window."
        )


def assert_attempts_available(
    placed_recently: int, settings: Settings | None = None
) -> None:
    """Refuse once a patient has been called enough times today."""
    settings = settings or get_settings()
    cap = settings.max_call_attempts_per_patient
    if placed_recently >= cap:
        raise PolicyRefusal(
            f"This patient has already been called {placed_recently} time(s) in "
            f"the last 24 hours, which is the cap "
            f"(MAX_CALL_ATTEMPTS_PER_PATIENT={cap})."
        )
