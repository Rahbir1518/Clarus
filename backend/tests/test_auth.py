"""Authentication.

The previous backend had none of this: every endpoint was reachable with a bare
curl. Each test here is a way in that used to work and must now fail.
"""
import pytest

from tests.conftest import TEST_AUDIENCE, TEST_ISSUER

PROTECTED = "/api/patients"


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
    response = client.get(PROTECTED, headers=auth_header("auth0|dr-alice"))
    assert response.status_code == 200


def test_expired_token_is_rejected(client, auth_header):
    response = client.get(
        PROTECTED, headers=auth_header("auth0|dr-alice", expires_in=-60)
    )
    assert response.status_code == 401


def test_token_for_another_audience_is_rejected(client, auth_header):
    """A token minted for a different API must not open this one."""
    response = client.get(
        PROTECTED,
        headers=auth_header("auth0|dr-alice", audience="https://some-other-api"),
    )
    assert response.status_code == 401


def test_token_from_another_issuer_is_rejected(client, auth_header):
    response = client.get(
        PROTECTED,
        headers=auth_header("auth0|dr-alice", issuer="https://attacker.example.com/"),
    )
    assert response.status_code == 401


def test_token_signed_with_a_different_key_is_rejected(client):
    """Correct claims, wrong signature."""
    import datetime as dt

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    forged = jwt.encode(
        {
            "sub": "auth0|dr-alice",
            "aud": TEST_AUDIENCE,
            "iss": TEST_ISSUER,
            "iat": now,
            "exp": now + dt.timedelta(hours=1),
        },
        attacker_key,
        algorithm="RS256",
    )

    response = client.get(PROTECTED, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_unsigned_token_is_rejected(client):
    """The alg=none attack."""
    import datetime as dt

    import jwt

    now = dt.datetime.now(dt.timezone.utc)
    unsigned = jwt.encode(
        {
            "sub": "auth0|dr-alice",
            "aud": TEST_AUDIENCE,
            "iss": TEST_ISSUER,
            "iat": now,
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
