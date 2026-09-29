"""Health endpoints are the only routes that may be reached without a token."""


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_configuration_without_revealing_it(client):
    response = client.get("/health/ready")
    assert response.status_code == 200

    body = response.json()
    assert body["checks"] == {
        "supabase_configured": True,
        "clerk_configured": True,
    }

    # An unauthenticated endpoint must not echo credentials or URLs back.
    serialised = response.text
    assert "test-service-role-key" not in serialised
    assert "supabase.co" not in serialised
