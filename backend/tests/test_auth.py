"""Authentication.

The previous backend had none of this: every endpoint was reachable with a bare
curl. Each test here is a way in that used to work and must now fail.

Tokens are real RS256 JWTs signed with a locally generated key and verified
through the real PyJWT path — only the JWKS endpoint is stubbed. The audience
checks that used to live here are gone: Clerk session tokens carry no `aud`,
and the `azp` tests below are what replaces them.
"""
import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.conftest import TEST_AUTHORIZED_PARTY, TEST_ISSUER

PROTECTED = "/api/patients"
ALICE = "user_2alice"


def test_no_token_is_rejected(client):
    response = client.get(PROTECTED)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_rejected(client):
    response = client.get(PROTECTED, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_non_bearer_scheme_is_rejected(client):
    response = client.get(PROTECTED, headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_valid_token_is_accepted(client, auth_header):
    response = client.get(PROTECTED, headers=auth_header(ALICE))
    assert response.status_code == 200


def test_expired_token_is_rejected(client, auth_header):
    response = client.get(PROTECTED, headers=auth_header(ALICE, expires_in=-60))
    assert response.status_code == 401


def test_token_not_yet_valid_is_rejected(client, auth_header):
    """Clerk sets nbf. A token from the future must not be honoured — beyond
    the few seconds of leeway allowed for clock drift."""
    response = client.get(PROTECTED, headers=auth_header(ALICE, not_before=120))
    assert response.status_code == 401


def test_small_clock_skew_is_tolerated(client, auth_header):
    """...but a couple of seconds of drift must not 401 a legitimate user."""
    response = client.get(PROTECTED, headers=auth_header(ALICE, not_before=-2))
    assert response.status_code == 200


def test_token_from_another_issuer_is_rejected(client, auth_header):
    response = client.get(
        PROTECTED,
        headers=auth_header(ALICE, issuer="https://attacker.clerk.accounts.dev"),
    )
    assert response.status_code == 401


def test_token_for_another_origin_is_rejected(client, auth_header):
    """azp is Clerk's replacement for an audience check. A token minted for a
    different app on the same Clerk instance must not open this API."""
    response = client.get(
        PROTECTED, headers=auth_header(ALICE, azp="https://someone-elses-app.com")
    )
    assert response.status_code == 401


def test_token_with_no_authorized_party_is_rejected(client, auth_header):
    """Omitting the claim must not be a way around the check."""
    response = client.get(PROTECTED, headers=auth_header(ALICE, azp=None))
    assert response.status_code == 401


def test_authorized_party_is_accepted(client, auth_header):
    response = client.get(
        PROTECTED, headers=auth_header(ALICE, azp=TEST_AUTHORIZED_PARTY)
    )
    assert response.status_code == 200


def test_token_without_a_subject_is_rejected(client, auth_header):
    response = client.get(PROTECTED, headers=auth_header(ALICE, sub=""))
    assert response.status_code == 401


def _forged(key, **overrides) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    claims = {
        "sub": ALICE,
        "iss": TEST_ISSUER,
        "azp": TEST_AUTHORIZED_PARTY,
        "iat": now,
        "nbf": now,
        "exp": now + dt.timedelta(hours=1),
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm=overrides.pop("algorithm", "RS256"))


def test_token_signed_with_a_different_key_is_rejected(client):
    """Correct claims, wrong signature."""
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = client.get(
        PROTECTED, headers={"Authorization": f"Bearer {_forged(attacker_key)}"}
    )
    assert response.status_code == 401


def test_unsigned_token_is_rejected(client):
    """The alg=none attack."""
    now = dt.datetime.now(dt.timezone.utc)
    unsigned = jwt.encode(
        {
            "sub": ALICE,
            "iss": TEST_ISSUER,
            "azp": TEST_AUTHORIZED_PARTY,
            "iat": now,
            "nbf": now,
            "exp": now + dt.timedelta(hours=1),
        },
        key="",
        algorithm="none",
    )

    response = client.get(PROTECTED, headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/patients"),
        ("post", "/api/patients"),
        ("get", "/api/patients/some-id"),
        ("put", "/api/patients/some-id"),
        ("delete", "/api/patients/some-id"),
    ],
)
def test_every_patient_route_requires_auth(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} was reachable"
