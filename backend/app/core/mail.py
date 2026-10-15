"""Outgoing email, and what counts as an address worth sending to.

Two senders share this: the public contact form (routes/contact.py) and the
call links a patient answers in their own browser
(app/integrations/call_links.py). Both send through the one SMTP account in
settings — see the contact settings in app/core/config.py for why mail goes
out *from* that account rather than from anyone else's address.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings

# Deliberately conservative: a real address fits it, and nothing that could
# smuggle a header or a second recipient does.
_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,63}$"
)


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL.fullmatch(value)) and ".." not in value


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_username and settings.smtp_password)


def send_email(msg: EmailMessage, settings: Settings) -> None:
    """Send through the configured account. A function of its own so tests can
    replace it; raises smtplib.SMTPException or OSError when sending fails."""
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
