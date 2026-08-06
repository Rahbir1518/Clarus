"""Shared request-model pieces.

Extracted when the third resource needed them. The pattern that matters is
`extra="ignore"`: the frontend sends `doctor_id` in several create payloads,
and dropping it here is what lets the tenant key come from the verified token
instead. Rejecting the field would break those callers; honouring it would be
the vulnerability.
"""
from typing import Any

from pydantic import ConfigDict

REQUEST_CONFIG = ConfigDict(extra="ignore", str_strip_whitespace=True)
READ_CONFIG = ConfigDict(extra="ignore")


def blank_to_none(value: Any) -> Any:
    """HTML form fields submit "" where the API means "no value".

    Without this, an untouched optional date input arrives as an empty string
    and fails date parsing as a 422 — on a field the user never filled in.
    """
    return None if isinstance(value, str) and not value.strip() else value
