"""Workflow CRUD through the HTTP API."""
from app.db.tenancy import TenantScope

ALICE = "user_2alice"
BOB = "user_2bob"


def _create(client, headers, **overrides) -> dict:
    payload = {"name": "Lab follow-up", **overrides}
    return client.post("/api/workflows", json=payload, headers=headers).json()


def test_a_workflow_belongs_to_the_token_subject(client, auth_header):
    """The frontend sends doctor_id in the create payload. It is ignored."""
    created = _create(client, auth_header(ALICE), doctor_id=BOB)

    assert created["doctor_id"] == ALICE
    assert created["status"] == "DRAFT"


def test_the_graph_survives_a_round_trip(client, auth_header):
    """nodes and edges are the builder's own shape, stored and returned
    unchanged rather than remodelled here."""
    nodes = [{"id": "n1", "type": "trigger", "data": {"kind": "lab_result"}}]
    edges = [{"id": "e1", "source": "n1", "target": "n2"}]

    created = _create(client, auth_header(ALICE), nodes=nodes, edges=edges)

    assert created["nodes"] == nodes
    assert created["edges"] == edges


def test_the_list_is_scoped_and_filterable(client, auth_header):
    _create(client, auth_header(ALICE), name="Mine", status="ENABLED")
    _create(client, auth_header(ALICE), name="Draft")
    _create(client, auth_header(BOB), name="Theirs", status="ENABLED")

    body = client.get("/api/workflows?status=ENABLED", headers=auth_header(ALICE))

    assert [w["name"] for w in body.json()] == ["Mine"]


def test_an_unknown_status_is_refused(client, auth_header):
    """The CHECK constraint on workflows.status would reject this in the
    database as a 500. Catching it in Pydantic makes it a 422 naming the
    field."""
    response = client.post(
        "/api/workflows",
        json={"name": "W", "status": "PUBLISHED"},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 422


def test_a_partial_update_leaves_the_graph_alone(client, auth_header):
    """The triggers page toggles status without loading the graph. It must not
    blank the nodes it never had."""
    headers = auth_header(ALICE)
    created = _create(client, headers, nodes=[{"id": "n1"}])

    updated = client.put(
        f"/api/workflows/{created['id']}",
        json={"status": "ENABLED"},
        headers=headers,
    ).json()

    assert updated["status"] == "ENABLED"
    assert updated["nodes"] == [{"id": "n1"}]


def test_another_tenants_workflow_is_invisible(client, auth_header):
    created = _create(client, auth_header(BOB))
    headers = auth_header(ALICE)

    assert client.get(f"/api/workflows/{created['id']}", headers=headers).status_code == 404
    assert client.put(
        f"/api/workflows/{created['id']}", json={"name": "Hijacked"}, headers=headers
    ).status_code == 404
    assert client.delete(
        f"/api/workflows/{created['id']}", headers=headers
    ).status_code == 404


def test_delete_removes_the_row(client, fake_db, auth_header):
    """No deleted_at on workflows — retirement is status='ARCHIVED', so an
    actual DELETE is an actual delete."""
    headers = auth_header(ALICE)
    created = _create(client, headers)

    assert client.delete(f"/api/workflows/{created['id']}", headers=headers).status_code == 204
    assert fake_db.store["workflows"] == []


def test_workflows_require_a_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/workflows").status_code == 401


def test_a_call_log_may_reference_an_owned_workflow(client, fake_db, auth_header):
    """The engine will link the two. Confirms the reference check accepts the
    legitimate case rather than only refusing the forged one."""
    created = _create(client, auth_header(ALICE))
    scope = TenantScope(fake_db, ALICE)

    log = scope.insert_owned(
        "call_logs", {"status": "pending", "workflow_id": created["id"]}
    )

    assert log["workflow_id"] == created["id"]
