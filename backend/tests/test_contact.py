"""The public contact form: it sends, and it does not become a spam cannon."""
import pytest

from app.api.routes import contact
from app.core.config import get_settings


@pytest.fixture
def sent(monkeypatch):
    """Configure SMTP and capture what would have been sent."""
    monkeypatch.setenv("SMTP_USERNAME", "info.cl4rus@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    get_settings.cache_clear()
    contact.limiter.reset()
    messages = []
    monkeypatch.setattr(contact, "send_email", lambda msg, settings: messages.append(msg))
    yield messages
    contact.limiter.reset()
    get_settings.cache_clear()


def _form(**overrides):
    body = {
        "name": "Dr. Priya Nair",
        "email": "priya@lakeviewclinic.com",
        "clinic": "Lakeview Family Clinic",
        "role": "physician",
        "interest": "demo",
        "message": "We'd like to see a demo for our clinic.",
        "hp_extra": "",
        "elapsed_ms": 12_000,
    }
    body.update(overrides)
    return body


def test_a_message_is_emailed_to_the_inbox_with_the_visitor_as_reply_to(client, sent):
    response = client.post("/api/contact", json=_form())

    assert response.status_code == 202
    [msg] = sent
    assert msg["To"] == "info.cl4rus@gmail.com"
    assert "info.cl4rus@gmail.com" in msg["From"]
    assert "priya@lakeviewclinic.com" in msg["Reply-To"]
    body = msg.get_content()
    assert "We'd like to see a demo" in body
    assert "Product demo" in body


@pytest.mark.parametrize("trap", [{"hp_extra": "http://spam.example"}, {"elapsed_ms": 500}])
def test_a_bot_is_told_it_worked_and_nothing_is_sent(client, sent, trap):
    response = client.post("/api/contact", json=_form(**trap))

    assert response.status_code == 202
    assert sent == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", "Mallory\r\nBcc: everyone@example.com"),
        ("clinic", "Clinic\nBcc: x@example.com"),
        ("email", "a@example.com\r\nBcc: x@example.com"),
        ("email", "a@example.com, b@example.com"),
        ("email", "not-an-email"),
        ("role", "admin\r\nX-Injected: 1"),
        ("message", "short"),
        ("message", "x" * 5001),
        ("message", "buy http://a.com http://b.com http://c.com www.d.com now"),
    ],
)
def test_header_injection_and_junk_are_refused(client, sent, field, value):
    response = client.post("/api/contact", json=_form(**{field: value}))

    assert response.status_code == 422
    assert sent == []


def test_unknown_fields_are_refused(client, sent):
    assert client.post("/api/contact", json=_form(bcc="x@example.com")).status_code == 422


def test_one_address_is_rate_limited(client, sent):
    limit = get_settings().contact_limit_per_ip_short
    for _ in range(limit):
        assert client.post("/api/contact", json=_form()).status_code == 202

    refused = client.post("/api/contact", json=_form())

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0
    assert len(sent) == limit


def test_bot_submissions_count_against_the_limit_too(client, sent):
    limit = get_settings().contact_limit_per_ip_short
    for _ in range(limit):
        client.post("/api/contact", json=_form(hp_extra="spam"))

    assert client.post("/api/contact", json=_form()).status_code == 429


def test_a_forwarded_for_header_is_ignored_unless_trusted(client, sent):
    limit = get_settings().contact_limit_per_ip_short
    for i in range(limit):
        client.post("/api/contact", json=_form(), headers={"X-Forwarded-For": f"10.0.0.{i}"})

    spoofed = client.post("/api/contact", json=_form(), headers={"X-Forwarded-For": "10.0.0.99"})

    assert spoofed.status_code == 429


def test_without_smtp_credentials_the_form_says_so(client, sent, monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "")
    get_settings.cache_clear()

    response = client.post("/api/contact", json=_form())

    assert response.status_code == 503
    assert sent == []


def test_an_smtp_failure_is_reported_without_leaking_details(client, sent, monkeypatch):
    def boom(msg, settings):
        raise contact.smtplib.SMTPAuthenticationError(535, b"secret server detail")

    monkeypatch.setattr(contact, "send_email", boom)

    response = client.post("/api/contact", json=_form())

    assert response.status_code == 502
    assert "secret" not in response.text
