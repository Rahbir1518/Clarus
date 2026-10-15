"""Call links: a patient answers a waiting call in their own browser.

On CALL_TRANSPORT=email a workflow's call_patient node parks the run exactly as
on CALL_TRANSPORT=web, then emails the patient a link. Opening it lets them
talk to the agent with no account and no app. From there it is the web call
path unchanged: the browser binds its conversation, and the post-call webhook
resumes the run.

The link is the credential, so it is built to be one:

  * **Signed.** `<call_log_id>.<expires>.<signature>`, an HMAC over both under
    CALL_LINK_SECRET. Changing either invalidates it, so a link names one call
    log and cannot be edited into another practice's.
  * **Expiring.** After CALL_LINK_TTL_HOURS it is refused, so a forwarded or
    leaked email stops being useful.
  * **Spent once used.** A link answers a call only while no conversation is
    bound to it. That is enforced on the row, not here — see
    routes/calls.py — because "used" is a fact about the call, not the link.

Derived rather than stored, like the run references in
app/integrations/elevenlabs/webhook.py: there is nothing new in the database to
keep secret, and rotating CALL_LINK_SECRET revokes every link at once.

Nothing clinical is ever in the email or behind the link. The email names the
practice and nothing else; what the agent says comes from the variables the
run stored, through the same vocabulary rules as every other call.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape

from app.core.config import Settings, require
from app.core.mail import send_email

# Where the frontend serves the page a link opens: app/call/[token]/page.tsx.
CALL_PAGE_PATH = "/call"


class CallLinkError(Exception):
    """A link that grants nothing. The message is safe to show its holder."""


class InvalidCallLink(CallLinkError):
    def __init__(self) -> None:
        super().__init__("This call link is not valid.")


class ExpiredCallLink(CallLinkError):
    def __init__(self) -> None:
        super().__init__("This call link has expired.")


@dataclass(frozen=True)
class CallLink:
    token: str
    url: str
    expires_at: datetime


def _signature(call_log_id: str, expires: int, secret: str) -> str:
    message = f"clarus-call-link:{call_log_id}:{expires}".encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue_call_link(
    call_log_id: str, settings: Settings, *, now: datetime | None = None
) -> CallLink:
    """A fresh link for one call log. Raises MissingConfiguration without a
    secret to sign it or a public address for it to point at."""
    require("call_link_secret", "public_app_url")
    expires_at = (now or datetime.now(timezone.utc)) + timedelta(
        hours=settings.call_link_ttl_hours
    )
    expires = int(expires_at.timestamp())
    token = f"{call_log_id}.{expires}.{_signature(call_log_id, expires, settings.call_link_secret)}"
    url = f"{settings.public_app_url.rstrip('/')}{CALL_PAGE_PATH}/{token}"
    return CallLink(token=token, url=url, expires_at=expires_at)


def read_call_link(token: str, settings: Settings, *, now: datetime | None = None) -> str:
    """The call log id a genuine, unexpired link names.

    The signature is checked before the expiry, so a forged link is told it is
    invalid whatever date it claims, and only a real one learns it has expired.
    """
    if not settings.call_link_secret:
        raise InvalidCallLink()
    call_log_id, _, rest = token.partition(".")
    expires_text, _, signature = rest.partition(".")
    if not call_log_id or not expires_text.isdigit() or not signature:
        raise InvalidCallLink()

    expires = int(expires_text)
    expected = _signature(call_log_id, expires, settings.call_link_secret)
    if not hmac.compare_digest(expected, signature):
        raise InvalidCallLink()
    if (now or datetime.now(timezone.utc)).timestamp() >= expires:
        raise ExpiredCallLink()
    return call_log_id


# ---------------------------------------------------------------------------
# The invitation email
# ---------------------------------------------------------------------------

# The patient's language follows their number, as the agent's does (see
# app.engine.policy.call_language). Nothing here names the patient or the
# reason for the call: if the address on file is wrong, a stranger learns only
# that a practice tried to reach someone.
_COPY = {
    "en": {
        "subject": "{practice} would like to speak with you",
        "greeting": "Hello,",
        "body": (
            "{practice} would like to speak with you about an appointment. "
            "Tap the button below to answer the call. It opens in your web "
            "browser, so there is nothing to install."
        ),
        "button": "Answer the call",
        "fallback": "If the button does not work, open this link:",
        "expiry": "The link can be used once and expires in {hours} hours.",
        "ignore": "If you were not expecting this, you can ignore this email.",
    },
    "bn": {
        "subject": "{practice} আপনার সাথে কথা বলতে চায়",
        "greeting": "আসসালামু আলাইকুম,",
        "body": (
            "{practice} একটি অ্যাপয়েন্টমেন্ট নিয়ে আপনার সাথে কথা বলতে চায়। "
            "কলটি ধরতে নিচের বোতামে চাপ দিন। কলটি আপনার ওয়েব ব্রাউজারে খুলবে, "
            "কোনো অ্যাপ ইনস্টল করতে হবে না।"
        ),
        "button": "কলটি ধরুন",
        "fallback": "বোতামটি কাজ না করলে এই লিংকটি খুলুন:",
        "expiry": "লিংকটি একবারই ব্যবহার করা যাবে এবং {hours} ঘণ্টা পর এর মেয়াদ শেষ হবে।",
        "ignore": "আপনি যদি এটি আশা না করে থাকেন, তাহলে এই ইমেইলটি উপেক্ষা করতে পারেন।",
    },
}


def build_invitation(
    *, to: str, link: CallLink, practice_name: str, language: str, settings: Settings
) -> EmailMessage:
    copy = {
        key: text.format(practice=practice_name, hours=settings.call_link_ttl_hours)
        for key, text in _COPY.get(language, _COPY["en"]).items()
    }

    msg = EmailMessage()
    msg["Subject"] = copy["subject"]
    msg["From"] = formataddr((practice_name, settings.smtp_username))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain="clarus.call")
    msg.set_content(
        "\n\n".join(
            [
                copy["greeting"],
                copy["body"],
                f"{copy['button']}: {link.url}",
                copy["expiry"],
                copy["ignore"],
            ]
        )
    )
    # The practice name is the doctor's own setting; escaped all the same,
    # since it lands in markup a mail client renders.
    html = {key: escape(text) for key, text in copy.items()}
    url = escape(link.url, quote=True)
    msg.add_alternative(
        f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#f5f5f4;font-family:Arial,sans-serif;color:#1c1917;">
    <div style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px;">
      <p style="margin:0 0 16px;font-size:16px;">{html["greeting"]}</p>
      <p style="margin:0 0 24px;font-size:16px;line-height:1.5;">{html["body"]}</p>
      <p style="margin:0 0 24px;text-align:center;">
        <a href="{url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;font-size:18px;font-weight:bold;padding:14px 28px;border-radius:999px;">{html["button"]}</a>
      </p>
      <p style="margin:0 0 8px;font-size:13px;color:#57534e;">{html["fallback"]}</p>
      <p style="margin:0 0 24px;font-size:13px;word-break:break-all;"><a href="{url}" style="color:#2563eb;">{url}</a></p>
      <p style="margin:0 0 8px;font-size:13px;color:#57534e;">{html["expiry"]}</p>
      <p style="margin:0;font-size:13px;color:#57534e;">{html["ignore"]}</p>
    </div>
  </body>
</html>
""",
        subtype="html",
    )
    return msg


def send_call_link(
    *, to: str, link: CallLink, practice_name: str, language: str, settings: Settings
) -> None:
    """Email a call link. Raises MissingConfiguration without an SMTP account,
    and smtplib.SMTPException or OSError if sending fails."""
    require("smtp_username", "smtp_password")
    send_email(
        build_invitation(
            to=to,
            link=link,
            practice_name=practice_name,
            language=language,
            settings=settings,
        ),
        settings,
    )
