"""The public site's contact form.

    POST /api/contact   email a visitor's message to the practice inbox

Unauthenticated, like /health: the people filling it in do not have accounts.
That makes it the one route anyone on the internet can make this server act
on, so it is defended in layers, cheapest first:

  * Rate limits per client IP (short window and daily) and across everyone
    (hourly). A refusal is a 429 with Retry-After.
  * A honeypot field humans never see and a minimum time on the form. Either
    tripping gets the same 202 a real message gets, and nothing is sent: a bot
    told it failed tries again differently, one told it succeeded moves on.
  * Strict validation: bounded lengths, closed choices for role and interest,
    unknown fields refused, and no line breaks or control characters in
    anything that reaches a mail header — which is what stops header
    injection (a name of "x\\r\\nBcc: everyone@…" turning the form into a
    relay). EmailMessage refuses such headers too; this refuses them first,
    with a 422 rather than a 500.
  * A cap on links in the message, the commonest mark of form spam.

The email is plain text only, so nothing a visitor types is rendered as HTML
in the inbox. It is sent by the practice's own account to itself with the
visitor as Reply-To — see the contact settings in app/core/config.py for why
it is not sent "from" the visitor.
"""
from __future__ import annotations

import logging
import math
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings, get_settings
from app.core.ratelimit import SlidingWindowLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])

limiter = SlidingWindowLimiter()

# A person reading the page and typing a message takes longer than this; a
# script posting the moment the page loads does not.
MIN_FILL_MS = 3000
MAX_LINKS = 3

# Deliberately conservative: a real address fits it, and nothing that could
# smuggle a header or a second recipient does.
_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,63}$"
)
# Any C0/C1 control character, which includes CR and LF.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# The same, minus newline and tab, which a message body may contain.
_BODY_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)

_ROLES = {"physician": "Physician", "admin": "Clinic Administrator", "it": "IT / Technical", "other": "Other"}
_INTERESTS = {
    "demo": "Product demo",
    "pricing": "Pricing information",
    "enterprise": "Enterprise plan",
    "integration": "Integration support",
    "other": "Something else",
}


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    clinic: str = Field(default="", max_length=150)
    role: Literal["", "physician", "admin", "it", "other"] = ""
    interest: Literal["", "demo", "pricing", "enterprise", "integration", "other"] = ""
    message: str = Field(min_length=10, max_length=5000)
    # Honeypot. Hidden from people; bots filling every field fill this. The
    # name means nothing to browser autofill on purpose: an earlier "website"
    # field was filled in by Chrome for real visitors, whose messages were then
    # silently dropped as a bot's.
    hp_extra: str = Field(default="", max_length=500)
    # Milliseconds between the form appearing and being sent.
    elapsed_ms: int = Field(default=0, ge=0)

    @field_validator("name", "clinic")
    @classmethod
    def _single_line(cls, value: str) -> str:
        if _CONTROL.search(value):
            raise ValueError("must be a single line of plain text")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        if not _EMAIL.fullmatch(value) or ".." in value:
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        if _BODY_CONTROL.search(value):
            raise ValueError("contains characters that are not allowed")
        if len(_LINK.findall(value)) > MAX_LINKS:
            raise ValueError(f"Please include no more than {MAX_LINKS} links")
        return value


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        # The right-most entry is the one our own proxy appended; anything to
        # its left came from the client and can say whatever it likes.
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def _check_rate(ip: str, settings: Settings) -> None:
    retry_after = limiter.hit(
        [
            (f"ip-short:{ip}", settings.contact_limit_per_ip_short, settings.contact_short_window_seconds),
            (f"ip-day:{ip}", settings.contact_limit_per_ip_daily, 86_400),
            ("global-hour", settings.contact_limit_global_hourly, 3_600),
        ]
    )
    if retry_after is not None:
        logger.warning("Contact form rate limit hit by %s", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many messages. Please wait a while and try again.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


def build_message(body: ContactRequest, settings: Settings) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"Clarus enquiry from {body.name}"
    msg["From"] = formataddr(("Clarus contact form", settings.smtp_username))
    msg["To"] = settings.contact_to_email
    msg["Reply-To"] = formataddr((body.name, body.email))
    msg["Message-ID"] = make_msgid(domain="clarus.contact")
    msg.set_content(
        "\n".join(
            [
                "New message from the Clarus contact form.",
                "Reply to this email to answer them directly.",
                "",
                f"Name:     {body.name}",
                f"Email:    {body.email}",
                f"Clinic:   {body.clinic or '-'}",
                f"Role:     {_ROLES.get(body.role, '-')}",
                f"Interest: {_INTERESTS.get(body.interest, '-')}",
                "",
                "Message:",
                body.message,
            ]
        )
    )
    return msg


def send_email(msg: EmailMessage, settings: Settings) -> None:
    """Send through the configured account. Separate so tests can replace it."""
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_contact(body: ContactRequest, request: Request) -> dict:
    settings = get_settings()
    ip = client_ip(request, settings)
    _check_rate(ip, settings)

    if body.hp_extra or body.elapsed_ms < MIN_FILL_MS:
        logger.info(
            "Contact form submission from %s dropped as automated (honeypot=%s, elapsed_ms=%s)",
            ip,
            bool(body.hp_extra),
            body.elapsed_ms,
        )
        return {"ok": True}

    if not settings.smtp_username or not settings.smtp_password:
        logger.error("Contact form used but SMTP_USERNAME/SMTP_PASSWORD are not set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The contact form is unavailable right now. Please email us directly.",
        )

    try:
        send_email(build_message(body, settings), settings)
    except (smtplib.SMTPException, OSError):
        # Never echo the SMTP error: it can name the account and the server.
        logger.exception("Contact form email could not be sent")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Your message could not be sent. Please try again later.",
        ) from None

    return {"ok": True}
