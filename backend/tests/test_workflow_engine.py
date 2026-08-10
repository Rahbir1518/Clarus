"""The workflow engine: graph walking, safety refusals, parking and resuming.

Grouped by the property under test rather than by module, because most of these
are only meaningful end to end — "the call log exists before the call is placed"
is a statement about the order two components run in, and a unit test of either
one cannot make it.

ElevenLabs is stubbed throughout. Nothing here places a call or spends credits.
The stub records what it was asked to say, which is how the safety tests check
that clinical text never reached it.

What this suite cannot do, and it matters: `FakeSupabase` validates no schema, so
a column the engine writes that does not exist in Postgres passes here. See
"Known gaps" in backend/STATUS.md. Every column written by this engine is either
already exercised by the webhook path or listed in `WRITABLE_COLUMNS`, but that
is an argument, not a test.
"""
import datetime as dt
import json
import time

import pytest

from app.core.config import get_settings
from app.db.tenancy import TenantScope
from app.engine import nodes as engine_nodes
from app.engine import policy
from app.engine.policy import PolicyRefusal
from app.integrations.elevenlabs.webhook import sign_payload
from tests.conftest import TEST_WEBHOOK_SECRET, FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"

ALLOWED_NUMBER = "+8801700000000"


# ---------------------------------------------------------------------------
# Fixtures and builders
# ---------------------------------------------------------------------------


class _StubElevenLabs:
    """Records every call it was asked to place, and places none."""

    def __init__(self, recorder: list[dict], db: FakeSupabase) -> None:
        self._recorder = recorder
        self._db = db

    def __call__(self, *_args, **_kwargs) -> "_StubElevenLabs":
        return self

    def outbound_call(self, *, to_number: str, dynamic_variables: dict, **_kw) -> dict:
        self._recorder.append(
            {
                "to_number": to_number,
                "dynamic_variables": dynamic_variables,
                # Snapshotted at the moment of dialling, which is the only point
                # at which "was the row created first?" can be answered.
                "call_logs_at_dial_time": [
                    dict(row) for row in self._db.store.get("call_logs", [])
                ],
            }
        )
        return {
            "success": True,
            "conversation_id": f"conv_{len(self._recorder)}",
            "callSid": "CA_stub",
        }


@pytest.fixture
def placed_calls(monkeypatch: pytest.MonkeyPatch, fake_db: FakeSupabase) -> list[dict]:
    recorder: list[dict] = []
    monkeypatch.setattr(
        engine_nodes, "ElevenLabsClient", _StubElevenLabs(recorder, fake_db)
    )
    return recorder


@pytest.fixture
def calling_allowed(monkeypatch: pytest.MonkeyPatch):
    """Every outbound gate open, through the real Settings parsing.

    Env vars and a cleared cache rather than a hand-built Settings object, so the
    booleans and the comma-separated list are parsed the way production parses
    them. A gate that only works because a test constructed its own settings is
    a gate that has not been tested.
    """
    monkeypatch.setenv("CALLS_ENABLED", "true")
    monkeypatch.setenv("CALL_ALLOWED_NUMBERS", ALLOWED_NUMBER)
    monkeypatch.setenv("CALLING_HOURS_START", "0")
    monkeypatch.setenv("CALLING_HOURS_END", "24")
    monkeypatch.setenv("PRACTICE_CALLBACK_NUMBER", "+8802000000000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _node(node_id: str, node_type: str, **params: str) -> dict:
    return {
        "id": node_id,
        # Presentation only. The engine reads data.nodeType and nothing else,
        # which is why every node here can claim to be an "action".
        "type": "action",
        "position": {"x": 0, "y": 0},
        "data": {"label": node_id, "nodeType": node_type, "params": params},
    }


def _edge(source: str, target: str, handle: str | None = None) -> dict:
    edge = {"id": f"{source}->{target}", "source": source, "target": target}
    if handle:
        edge["sourceHandle"] = handle
    return edge


def _patient(db: FakeSupabase, doctor_id: str = ALICE, **fields) -> dict:
    values = {"name": "রহিম", "phone": ALLOWED_NUMBER}
    values.update(fields)
    return TenantScope(db, doctor_id).insert_owned("patients", values)


def _workflow(
    db: FakeSupabase,
    nodes: list[dict],
    edges: list[dict],
    *,
    doctor_id: str = ALICE,
    status: str = "ENABLED",
    name: str = "Test workflow",
) -> dict:
    return TenantScope(db, doctor_id).insert_owned(
        "workflows",
        {"name": name, "status": status, "nodes": nodes, "edges": edges},
    )


def _run(client, auth_header, workflow_id: str, patient_id: str, **body):
    return client.post(
        f"/api/workflows/{workflow_id}/execute",
        json={"patient_id": patient_id, **body},
        headers=auth_header(ALICE),
    )


def _steps(response) -> list[dict]:
    return response.json()["execution_log"]


def _step_for(response, node_type: str) -> dict:
    return next(s for s in _steps(response) if s["node_type"] == node_type)


def _call_row(db: FakeSupabase, call_log_id: str) -> dict:
    return next(r for r in db.store["call_logs"] if r["id"] == call_log_id)


def _webhook(client, conversation_id: str, **collected):
    """Deliver a signed post-call webhook, the way ElevenLabs would."""
    values = {
        "patient_confirmed": True,
        "confirmed_date": "2026-08-14",
        "confirmed_time": "14:30",
        "call_outcome": "confirmed",
        "reached_patient": True,
        "callback_requested": False,
        "patient_availability_notes": None,
    }
    values.update(collected)
    body = json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": int(time.time()),
            "data": {
                "conversation_id": conversation_id,
                "status": "done",
                "transcript": [{"role": "user", "message": "হ্যাঁ, ঠিক আছে।"}],
                "analysis": {
                    "data_collection_results": {
                        key: {"value": value} for key, value in values.items()
                    }
                },
            },
        }
    ).encode()
    return client.post(
        "/api/elevenlabs/webhook",
        content=body,
        headers={
            "elevenlabs-signature": sign_payload(
                body, TEST_WEBHOOK_SECRET, int(time.time())
            ),
            "content-type": "application/json",
        },
    )


# A trigger, a call, and the two nodes that only make sense after one.
def _call_graph(**call_params: str) -> tuple[list[dict], list[dict]]:
    nodes = [
        _node("t1", "lab_results_received"),
        _node("c1", "call_patient", **call_params),
        _node("a1", "schedule_appointment", duration_minutes="20"),
        _node("s1", "send_summary_to_doctor"),
    ]
    edges = [_edge("t1", "c1"), _edge("c1", "a1"), _edge("a1", "s1")]
    return nodes, edges


# ---------------------------------------------------------------------------
# The graph has to be walkable before anything happens
# ---------------------------------------------------------------------------


def test_an_unknown_node_type_is_refused_before_anything_runs(
    client, fake_db, auth_header
):
    """Not skipped. A graph containing a node the engine does not recognise is
    not the graph its author believes it is, and it is about to phone somebody."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("x1", "hack_the_planet")],
        [_edge("t1", "x1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 422
    assert "hack_the_planet" in response.json()["error"]["message"]
    # And no run record for a workflow that never started.
    assert fake_db.store.get("call_logs", []) == []


def test_a_graph_with_no_trigger_is_refused(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, [_node("n1", "log_completion")], [])

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 422
    assert "trigger" in response.json()["error"]["message"]


def test_a_conditional_edge_with_no_handle_is_refused(client, fake_db, auth_header):
    """Which branch the author meant is not something to guess at."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("q1", "check_patient_age", operator="greater_than", threshold="60"),
            _node("e1", "log_completion"),
        ],
        [_edge("t1", "q1"), _edge("q1", "e1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 422
    assert "'true' or 'false' handle" in response.json()["error"]["message"]


def test_several_triggers_need_the_run_to_name_one(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("t2", "follow_up_due"),
            _node("e1", "log_completion"),
        ],
        [_edge("t1", "e1"), _edge("t2", "e1")],
    )

    ambiguous = _run(client, auth_header, workflow["id"], patient["id"])
    assert ambiguous.status_code == 422

    named = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        trigger_node_type="follow_up_due",
    )
    assert named.status_code == 200
    # The named trigger ran and the other one did not — the parameter is
    # honoured, which the previous system documented and then ignored.
    assert _step_for(named, "follow_up_due")["status"] == "ok"
    assert not any(s["node_type"] == "lab_results_received" for s in _steps(named))


def test_the_trigger_a_run_names_must_exist_in_the_graph(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
    )

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        trigger_node_type="prescription_expiring",
    )

    # Not a fallback to the only trigger there is. A prescription-expiry event
    # must not run a lab-results workflow because the names did not match.
    assert response.status_code == 422


def test_an_archived_workflow_will_not_run(client, fake_db, auth_header):
    patient = _patient(fake_db)
    nodes, edges = _call_graph()
    workflow = _workflow(fake_db, nodes, edges, status="ARCHIVED")

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 409


def test_executing_another_practices_workflow_is_a_404(client, fake_db, auth_header):
    patient = _patient(fake_db, BOB)
    workflow = _workflow(fake_db, *_call_graph(), doctor_id=BOB)

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 404
    assert fake_db.store.get("call_logs", []) == []


def test_running_a_workflow_requires_authentication(client, fake_db):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())

    response = client.post(
        f"/api/workflows/{workflow['id']}/execute", json={"patient_id": patient["id"]}
    )

    assert response.status_code == 401
    assert fake_db.store.get("call_logs", []) == []


# ---------------------------------------------------------------------------
# The run record, and the order it is created in
# ---------------------------------------------------------------------------


def test_the_call_log_exists_before_the_call_is_placed(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The gap this engine was written to close.

    The webhook can only complete a row that already exists, so a row written
    after the provider is asked to dial is a race with a ringing phone on the
    other side of it.
    """
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())

    response = _run(client, auth_header, workflow["id"], patient["id"])
    call_log_id = response.json()["call_log_id"]

    assert len(placed_calls) == 1
    rows_at_dial_time = placed_calls[0]["call_logs_at_dial_time"]
    assert [r["id"] for r in rows_at_dial_time] == [call_log_id]
    # And it was already in the state that says a call is in flight.
    assert rows_at_dial_time[0]["status"] == "in_progress"


def test_a_run_that_places_no_call_still_records_itself(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [_node("t1", "follow_up_due"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.json()["status"] == "completed"
    row = _call_row(fake_db, response.json()["call_log_id"])
    assert row["status"] == "completed"
    assert row["trigger_node"] == "follow_up_due"
    # A run that completed cleanly and rang nobody is not a review item.
    assert row["needs_review"] is False


def test_the_execution_log_records_every_step_in_order(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("n1", "send_notification", message="Results are in", recipient="nurse"),
            _node("e1", "log_completion"),
        ],
        [_edge("t1", "n1"), _edge("n1", "e1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])
    steps = _steps(response)

    assert [s["node_type"] for s in steps] == [
        "run.started",
        "lab_results_received",
        "send_notification",
        "log_completion",
        "run.finished",
    ]
    # seq is contiguous and independent of array position, because the array is
    # written across two requests when a run parks.
    assert [s["seq"] for s in steps] == list(range(len(steps)))

    # The fields the builder's run panel reads.
    for step in steps:
        assert set(step) >= {"status", "label", "node_type", "message"}

    # A step that created a row says which row, and never what was in it.
    notification = _step_for(response, "send_notification")
    assert notification["entity"]["table"] == "notifications"
    assert notification["entity"]["id"]

    # The log is persisted, not just returned.
    assert _call_row(fake_db, response.json()["call_log_id"])["execution_log"] == steps


def test_the_run_pins_the_graph_it_executed(client, fake_db, auth_header):
    """A workflow is editable after it has run. Without the fingerprint, a past
    run cannot be explained, because its definition has moved."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, [_node("t1", "follow_up_due")], [])

    response = _run(client, auth_header, workflow["id"], patient["id"])

    started = _step_for(response, "run.started")
    assert started["data"]["fingerprint"]
    assert started["data"]["trigger_node_type"] == "follow_up_due"


def test_a_failed_step_halts_its_branch(client, fake_db, auth_header):
    """"Send the summary" must not run after a step that did not happen."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("m1", "send_sms", message="Your results are ready"),
            _node("e1", "log_completion"),
        ],
        [_edge("t1", "m1"), _edge("m1", "e1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.json()["status"] == "failed"
    assert _step_for(response, "send_sms")["status"] == "failed"
    assert not any(s["node_type"] == "log_completion" for s in _steps(response))
    assert _call_row(fake_db, response.json()["call_log_id"])["needs_review"] is True


def test_a_halted_branch_does_not_stop_a_parallel_one(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("m1", "send_sms", message="x"),
            _node("e1", "log_completion"),
        ],
        [_edge("t1", "m1"), _edge("t1", "e1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "send_sms")["status"] == "failed"
    assert _step_for(response, "log_completion")["status"] == "ok"


def test_a_node_reachable_twice_runs_once(client, fake_db, auth_header):
    """A graph where a node is reachable by two paths must not do its work twice
    just because both were drawn."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("n1", "send_notification", message="one"),
            _node("n2", "send_notification", message="two"),
            _node("j1", "log_completion"),
        ],
        [_edge("t1", "n1"), _edge("t1", "n2"), _edge("n1", "j1"), _edge("n2", "j1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])
    completions = [s for s in _steps(response) if s["node_id"] == "j1"]

    assert [s["status"] for s in completions] == ["ok", "skipped"]


def test_a_cycle_terminates(client, fake_db, auth_header):
    """A cycle in a graph that places calls is an unbounded number of calls."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("a", "log_completion"),
            _node("b", "log_completion"),
        ],
        [_edge("t1", "a"), _edge("a", "b"), _edge("b", "a")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert response.status_code == 200
    assert len(_steps(response)) < 10


# ---------------------------------------------------------------------------
# Conditionals
# ---------------------------------------------------------------------------


def _threshold_graph(**params: str) -> tuple[list[dict], list[dict]]:
    nodes = [
        _node("t1", "lab_results_received"),
        _node("q1", "check_result_values", **params),
        _node("hi", "send_notification", message="above threshold"),
        _node("lo", "log_completion"),
    ]
    edges = [_edge("t1", "q1"), _edge("q1", "hi", "true"), _edge("q1", "lo", "false")]
    return nodes, edges


def test_a_threshold_takes_the_branch_the_values_support(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        *_threshold_graph(
            test_name="HbA1c",
            operator="greater_than",
            threshold="7",
            abnormal_branch="none",
        ),
    )

    high = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"hba1c": 8.2}},
    )
    assert _step_for(high, "check_result_values")["branch"] == "true"
    assert any(s["node_id"] == "hi" for s in _steps(high))

    low = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": [{"test": "HbA1c", "value": "6.1"}]},
    )
    assert _step_for(low, "check_result_values")["branch"] == "false"
    assert any(s["node_id"] == "lo" for s in _steps(low))


def test_a_missing_value_blocks_rather_than_reading_as_normal(
    client, fake_db, auth_header
):
    """The failure this exists to prevent: an absent value read as a negative,
    so a system decides a result is normal because it could not find it."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db, *_threshold_graph(test_name="HbA1c", operator="greater_than", threshold="7")
    )

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"creatinine": 1.1}},
    )

    step = _step_for(response, "check_result_values")
    assert step["status"] == "blocked"
    assert step["branch"] is None
    # Neither branch ran.
    assert not any(s["node_id"] in {"hi", "lo"} for s in _steps(response))
    assert response.json()["status"] == "blocked"
    assert _call_row(fake_db, response.json()["call_log_id"])["needs_review"] is True


def test_a_non_numeric_value_is_treated_as_absent(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db, *_threshold_graph(test_name="HbA1c", operator="greater_than", threshold="7")
    )

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"hba1c": "pending"}},
    )

    assert _step_for(response, "check_result_values")["status"] == "blocked"


def test_a_conditional_on_the_patient_record_branches(client, fake_db, auth_header):
    born = dt.date.today().replace(year=dt.date.today().year - 70).isoformat()
    patient = _patient(fake_db, dob=born)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "follow_up_due"),
            _node("q1", "check_patient_age", operator="greater_than", threshold="65"),
            _node("hi", "log_completion"),
            _node("lo", "send_sms", message="never reached"),
        ],
        [_edge("t1", "q1"), _edge("q1", "hi", "true"), _edge("q1", "lo", "false")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "check_patient_age")["branch"] == "true"
    assert response.json()["status"] == "completed"


def test_an_age_condition_on_a_patient_with_no_dob_blocks(
    client, fake_db, auth_header
):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "follow_up_due"),
            _node("q1", "check_patient_age", operator="greater_than", threshold="65"),
            _node("lo", "log_completion"),
        ],
        [_edge("t1", "q1"), _edge("q1", "lo", "false")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "check_patient_age")["status"] == "blocked"


def test_a_missing_required_parameter_blocks_the_node(client, fake_db, auth_header):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("n1", "send_notification", message=""),
        ],
        [_edge("t1", "n1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    step = _step_for(response, "send_notification")
    assert step["status"] == "blocked"
    assert "message" in step["message"]


# ---------------------------------------------------------------------------
# The safety policy — AI_CALL_SAFETY_POLICY.md
# ---------------------------------------------------------------------------


def test_clinical_content_on_a_call_node_is_refused_not_stripped(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The parameter this policy was written about.

    Stripping it silently was the alternative: the author would then believe a
    summary they wrote had been read to the patient.
    """
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db, *_call_graph(lab_result_summary="Cholesterol 6.8, elevated")
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    step = _step_for(response, "call_patient")
    assert step["status"] == "blocked"
    assert "lab_result_summary" in step["message"]
    assert placed_calls == []
    assert _call_row(fake_db, response.json()["call_log_id"])["needs_review"] is True


def test_an_empty_clinical_parameter_does_not_block(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The builder writes every declared parameter, blank ones included. A graph
    that has the field but does not use it is not carrying clinical content."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph(lab_result_summary=""))

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "call_patient")["status"] == "parked"
    assert len(placed_calls) == 1


def test_only_a_phrase_from_the_vocabulary_reaches_the_agent(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph(reason_code="follow_up"))

    _run(client, auth_header, workflow["id"], patient["id"])

    spoken = placed_calls[0]["dynamic_variables"]
    assert spoken["appointment_reason"] == policy.ALLOWED_CALL_REASONS["follow_up"]
    # Nothing the workflow author wrote is in what the agent says.
    assert set(spoken) == {
        "patient_name",
        "doctor_name",
        "practice_name",
        "appointment_reason",
        "callback_number",
        "timezone",
        "today_date",
    }


def test_an_unrecognised_reason_code_is_refused_not_defaulted(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """A typo must not silently change what a patient is told."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph(reason_code="results_are_abnormal"))

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "call_patient")["status"] == "blocked"
    assert placed_calls == []


def test_an_abnormal_trigger_never_places_a_call(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    nodes, edges = _call_graph()
    nodes[0] = _node("t1", "abnormal_result_detected")
    workflow = _workflow(fake_db, nodes, edges)

    response = _run(client, auth_header, workflow["id"], patient["id"])

    step = _step_for(response, "call_patient")
    assert step["status"] == "blocked"
    assert "abnormal" in step["message"]
    assert placed_calls == []
    assert _call_row(fake_db, response.json()["call_log_id"])["needs_review"] is True


def test_an_event_marked_abnormal_never_places_a_call(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"abnormal": True},
    )

    assert _step_for(response, "call_patient")["status"] == "blocked"
    assert placed_calls == []


def test_the_abnormal_branch_of_a_threshold_never_places_a_call(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """Default `abnormal_branch` is the true branch — the one where the threshold
    is met — because that is how these graphs are drawn and because defaulting
    the other way would place calls on abnormal paths until somebody noticed."""
    patient = _patient(fake_db)
    call_nodes, call_edges = _call_graph()
    nodes = [
        _node("q1", "check_result_values", test_name="HbA1c", operator="greater_than", threshold="7"),
        *call_nodes,
        _node("lo", "log_completion"),
    ]
    edges = [
        _edge("t1", "q1"),
        _edge("q1", "c1", "true"),
        _edge("q1", "lo", "false"),
        *[e for e in call_edges if e["source"] != "t1"],
    ]
    workflow = _workflow(fake_db, nodes, edges)

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"hba1c": 9.4}},
    )

    assert _step_for(response, "check_result_values")["branch"] == "true"
    assert _step_for(response, "call_patient")["status"] == "blocked"
    assert placed_calls == []


def test_the_normal_branch_of_a_threshold_may_call(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The intended flagship path: results are ready, nothing abnormal, book a
    time — and the agent says nothing about what the results were."""
    patient = _patient(fake_db)
    call_nodes, call_edges = _call_graph()
    nodes = [
        _node("q1", "check_result_values", test_name="HbA1c", operator="greater_than", threshold="7"),
        *call_nodes,
        _node("hi", "send_notification", message="HbA1c above range — review"),
    ]
    edges = [
        _edge("t1", "q1"),
        _edge("q1", "hi", "true"),
        _edge("q1", "c1", "false"),
        *[e for e in call_edges if e["source"] != "t1"],
    ]
    workflow = _workflow(fake_db, nodes, edges)

    response = _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"hba1c": 5.4}},
    )

    assert _step_for(response, "call_patient")["status"] == "parked"
    assert len(placed_calls) == 1
    spoken = " ".join(placed_calls[0]["dynamic_variables"].values())
    assert "5.4" not in spoken and "hba1c" not in spoken.lower()


def test_one_call_per_run(client, fake_db, auth_header, placed_calls, calling_allowed):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "lab_results_received"),
            _node("c1", "call_patient"),
            _node("c2", "call_patient"),
        ],
        [_edge("t1", "c1"), _edge("t1", "c2")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])
    statuses = [s["status"] for s in _steps(response) if s["node_type"] == "call_patient"]

    # conversation_id is write-once, so a second call's outcome could never be
    # matched to this run. Refused rather than placed with nowhere to report to.
    assert sorted(statuses) == ["blocked", "parked"]
    assert len(placed_calls) == 1


# -- the outbound gates ------------------------------------------------------


def test_the_kill_switch_stops_every_call(
    client, fake_db, auth_header, placed_calls, monkeypatch
):
    monkeypatch.setenv("CALLS_ENABLED", "false")
    monkeypatch.setenv("CALL_ALLOWED_NUMBERS", ALLOWED_NUMBER)
    get_settings.cache_clear()
    try:
        patient = _patient(fake_db)
        workflow = _workflow(fake_db, *_call_graph())

        response = _run(client, auth_header, workflow["id"], patient["id"])

        assert _step_for(response, "call_patient")["status"] == "blocked"
        assert placed_calls == []
    finally:
        get_settings.cache_clear()


def test_calls_are_off_by_default(client, fake_db, auth_header, placed_calls):
    """A fresh checkout, a new environment, or a forgotten variable places no
    calls. Every one of these settings must fail towards fewer calls."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "call_patient")["status"] == "blocked"
    assert placed_calls == []


def test_a_number_off_the_allowlist_is_refused(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db, phone="+8801799999999")
    workflow = _workflow(fake_db, *_call_graph())

    response = _run(client, auth_header, workflow["id"], patient["id"])

    step = _step_for(response, "call_patient")
    assert step["status"] == "blocked"
    assert "allowlist" in step["message"]
    assert placed_calls == []


def test_an_empty_allowlist_means_nothing_is_callable(
    client, fake_db, auth_header, placed_calls, monkeypatch
):
    monkeypatch.setenv("CALLS_ENABLED", "true")
    monkeypatch.setenv("CALL_ALLOWED_NUMBERS", "")
    get_settings.cache_clear()
    try:
        patient = _patient(fake_db)
        workflow = _workflow(fake_db, *_call_graph())

        response = _run(client, auth_header, workflow["id"], patient["id"])

        assert _step_for(response, "call_patient")["status"] == "blocked"
        assert placed_calls == []
    finally:
        get_settings.cache_clear()


def test_a_number_with_no_country_code_is_refused(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """Which country to assume is the guess that rings a stranger holding that
    number somewhere else."""
    patient = _patient(fake_db, phone="01700000000")
    workflow = _workflow(fake_db, *_call_graph())

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "call_patient")["status"] == "blocked"
    assert placed_calls == []


def test_the_attempt_cap_counts_calls_that_were_actually_placed(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())
    cap = get_settings().max_call_attempts_per_patient

    for _ in range(cap):
        response = _run(client, auth_header, workflow["id"], patient["id"])
        assert _step_for(response, "call_patient")["status"] == "parked"

    over = _run(client, auth_header, workflow["id"], patient["id"])
    step = _step_for(over, "call_patient")
    assert step["status"] == "blocked"
    assert "cap" in step["message"]
    assert len(placed_calls) == cap


def test_a_blocked_run_does_not_consume_an_attempt(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    blocked_workflow = _workflow(
        fake_db, *_call_graph(lab_result_summary="something clinical")
    )
    ok_workflow = _workflow(fake_db, *_call_graph())
    cap = get_settings().max_call_attempts_per_patient

    for _ in range(cap + 2):
        _run(client, auth_header, blocked_workflow["id"], patient["id"])

    response = _run(client, auth_header, ok_workflow["id"], patient["id"])
    assert _step_for(response, "call_patient")["status"] == "parked"


def test_calling_hours_are_measured_in_the_local_zone():
    """A unit test with an explicit clock: the window is the point, and a test
    that depends on when it runs proves nothing about the boundary."""
    zone = policy.calling_zone()
    settings = get_settings()

    inside = dt.datetime(2026, 8, 9, 11, 0, tzinfo=zone)
    policy.assert_within_calling_hours(inside, settings)

    with pytest.raises(PolicyRefusal, match="calling window"):
        policy.assert_within_calling_hours(
            dt.datetime(2026, 8, 9, 3, 0, tzinfo=zone), settings
        )
    # End is exclusive.
    with pytest.raises(PolicyRefusal, match="calling window"):
        policy.assert_within_calling_hours(
            dt.datetime(2026, 8, 9, settings.calling_hours_end, 0, tzinfo=zone),
            settings,
        )


def test_a_transposed_calling_window_refuses_rather_than_wrapping(monkeypatch):
    """Wrapping around midnight would turn two transposed numbers into
    permission to call all night."""
    monkeypatch.setenv("CALLING_HOURS_START", "20")
    monkeypatch.setenv("CALLING_HOURS_END", "9")
    get_settings.cache_clear()
    try:
        with pytest.raises(PolicyRefusal, match="not a valid window"):
            policy.assert_within_calling_hours(settings=get_settings())
    finally:
        get_settings.cache_clear()


def test_phone_numbers_are_normalised_before_comparison():
    assert policy.normalise_phone("(416) 555-0134") == "4165550134"
    assert policy.normalise_phone("+880 17-000 000 00") == "+8801700000000"
    assert policy.normalise_phone("008801700000000") == "+8801700000000"
    assert policy.normalise_phone(None) == ""


# ---------------------------------------------------------------------------
# Parking and resuming
# ---------------------------------------------------------------------------


def test_a_call_parks_the_run_and_the_webhook_resumes_it(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The whole point of the exercise: the patient agrees to a time on the call,
    and something acts on it. Before this, the agreement was recorded and then
    nothing happened."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())

    started = _run(client, auth_header, workflow["id"], patient["id"])
    call_log_id = started.json()["call_log_id"]

    assert started.json()["status"] == "parked"
    # The nodes after the call have not run yet.
    assert not any(s["node_type"] == "schedule_appointment" for s in _steps(started))

    assert _webhook(client, "conv_1").status_code == 204

    row = _call_row(fake_db, call_log_id)
    log = row["execution_log"]
    types = [s["node_type"] for s in log]
    assert "run.resumed" in types
    assert "schedule_appointment" in types
    assert "send_summary_to_doctor" in types

    appointment = fake_db.store["appointments"][0]
    assert appointment["doctor_id"] == ALICE
    assert appointment["patient_id"] == patient["id"]
    assert appointment["call_log_id"] == call_log_id
    assert appointment["status"] == "confirmed"
    assert appointment["starts_at"].startswith("2026-08-14T14:30")
    # 20 minutes, from the node's duration_minutes.
    assert appointment["ends_at"].startswith("2026-08-14T14:50")

    # seq keeps counting across the two requests rather than restarting.
    assert [s["seq"] for s in log] == list(range(len(log)))
    # The call completed and needs nobody's attention.
    assert row["status"] == "completed"
    assert row["needs_review"] is False


def test_a_call_that_reached_nobody_books_nothing_and_asks_for_a_human(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())
    call_log_id = _run(client, auth_header, workflow["id"], patient["id"]).json()[
        "call_log_id"
    ]

    _webhook(
        client,
        "conv_1",
        patient_confirmed=None,
        confirmed_date=None,
        confirmed_time=None,
        call_outcome="voicemail",
        reached_patient=False,
    )

    row = _call_row(fake_db, call_log_id)
    assert fake_db.store.get("appointments", []) == []
    assert row["needs_review"] is True
    step = next(
        s for s in row["execution_log"] if s["node_type"] == "schedule_appointment"
    )
    assert step["status"] == "skipped"
    # And the branch stopped there rather than summarising a call that never
    # reached anyone.
    assert any(s["node_type"] == "send_summary_to_doctor" for s in row["execution_log"])


def test_a_confirmation_with_no_pinned_time_is_not_booked(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """The old system's failure: booking off the word "yes" with a time nobody
    ever agreed to."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())
    _run(client, auth_header, workflow["id"], patient["id"])

    _webhook(client, "conv_1", confirmed_time=None)

    assert fake_db.store.get("appointments", []) == []


def test_a_second_webhook_delivery_does_not_run_the_graph_twice(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """Providers deliver twice. A second appointment for the same call would be
    a patient told to come in once and booked in twice."""
    patient = _patient(fake_db)
    workflow = _workflow(fake_db, *_call_graph())
    _run(client, auth_header, workflow["id"], patient["id"])

    assert _webhook(client, "conv_1").status_code == 204
    assert _webhook(client, "conv_1").status_code == 204

    assert len(fake_db.store["appointments"]) == 1


def test_editing_the_workflow_mid_call_stops_the_resume(
    client, fake_db, auth_header, placed_calls, calling_allowed
):
    """Resuming would execute a graph this run did not start on, and no copy of
    the one it did start on is kept. A person gets to see both instead."""
    patient = _patient(fake_db)
    nodes, edges = _call_graph()
    workflow = _workflow(fake_db, nodes, edges)
    call_log_id = _run(client, auth_header, workflow["id"], patient["id"]).json()[
        "call_log_id"
    ]

    TenantScope(fake_db, ALICE).update_owned(
        "workflows",
        workflow["id"],
        {"nodes": nodes + [_node("extra", "log_completion")], "edges": edges},
    )

    assert _webhook(client, "conv_1").status_code == 204

    row = _call_row(fake_db, call_log_id)
    resumed = next(s for s in row["execution_log"] if s["node_type"] == "run.resumed")
    assert resumed["status"] == "blocked"
    assert "workflow changed" in resumed["message"]
    assert fake_db.store.get("appointments", []) == []
    assert row["needs_review"] is True


def test_a_web_call_has_nothing_to_resume(client, fake_db, auth_header, monkeypatch):
    """Every call from routes/calls.py has no workflow. That is ordinary, and the
    webhook must still answer 204."""
    from app.api.routes import calls as calls_route

    class _StubToken:
        def __init__(self, *_a, **_k) -> None:
            pass

        def conversation_token(self, agent_id=None) -> str:
            return "tok_stub"

    monkeypatch.setattr(calls_route, "ElevenLabsClient", _StubToken)
    patient = _patient(fake_db)

    started = client.post(
        "/api/calls/web",
        json={"patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )
    call_log_id = started.json()["call_log_id"]
    client.post(
        f"/api/calls/web/{call_log_id}/bind",
        json={"conversation_id": "conv_web"},
        headers=auth_header(ALICE),
    )

    assert _webhook(client, "conv_web").status_code == 204
    assert _call_row(fake_db, call_log_id)["status"] == "completed"


def test_a_webhook_for_a_call_nobody_placed_is_acknowledged(client, fake_db):
    """A 4xx here would tell an unauthenticated caller whether a conversation id
    exists, and would have the provider retry for ever."""
    assert _webhook(client, "conv_unknown").status_code == 204


# ---------------------------------------------------------------------------
# POST /api/lab-event
# ---------------------------------------------------------------------------


def test_a_lab_event_runs_every_enabled_workflow_that_listens(
    client, fake_db, auth_header
):
    patient = _patient(fake_db)
    listening = _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
        name="Listening",
    )
    _workflow(
        fake_db,
        [_node("t1", "prescription_expiring"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
        name="Different trigger",
    )

    response = client.post(
        "/api/lab-event",
        json={"trigger_type": "lab_results_received", "patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    body = response.json()
    assert body["matched"] == 1
    assert body["runs"][0]["workflow_id"] == listening["id"]
    assert body["runs"][0]["status"] == "completed"


def test_a_lab_event_does_not_run_a_draft(client, fake_db, auth_header):
    """A half-drawn workflow must not start phoning patients because an event
    arrived. The builder's own Run button is how a draft gets tested."""
    patient = _patient(fake_db)
    _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
        status="DRAFT",
    )

    response = client.post(
        "/api/lab-event",
        json={"trigger_type": "lab_results_received", "patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    assert response.json()["matched"] == 0
    assert fake_db.store.get("call_logs", []) == []


def test_a_lab_event_never_crosses_a_tenant(client, fake_db, auth_header):
    patient = _patient(fake_db)
    _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
        doctor_id=BOB,
    )

    response = client.post(
        "/api/lab-event",
        json={"trigger_type": "lab_results_received", "patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    assert response.json()["matched"] == 0


def test_a_doctor_id_in_a_lab_event_body_is_ignored(client, fake_db, auth_header):
    """The frontend sends one. Honouring it would be the vulnerability; rejecting
    it would break the caller."""
    patient = _patient(fake_db)
    _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("e1", "log_completion")],
        [_edge("t1", "e1")],
    )

    response = client.post(
        "/api/lab-event",
        json={
            "trigger_type": "lab_results_received",
            "patient_id": patient["id"],
            "doctor_id": BOB,
        },
        headers=auth_header(ALICE),
    )

    assert response.json()["matched"] == 1
    assert all(row["doctor_id"] == ALICE for row in fake_db.store["call_logs"])


def test_an_unknown_trigger_type_is_a_422_not_an_empty_match(
    client, fake_db, auth_header
):
    """"Nothing listens for this" and "that trigger does not exist" look the same
    from outside and need different fixes."""
    patient = _patient(fake_db)

    response = client.post(
        "/api/lab-event",
        json={"trigger_type": "lab_results_recieved", "patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 422


def test_an_enabled_workflow_that_cannot_be_walked_is_reported(
    client, fake_db, auth_header
):
    """An enabled workflow that silently never fires is the thing nobody
    discovers until they ask why a patient was not called."""
    patient = _patient(fake_db)
    broken = _workflow(
        fake_db,
        [_node("t1", "lab_results_received"), _node("x1", "not_a_real_node")],
        [_edge("t1", "x1")],
        name="Broken",
    )

    response = client.post(
        "/api/lab-event",
        json={"trigger_type": "lab_results_received", "patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    body = response.json()
    assert body["matched"] == 0
    assert body["unrunnable"][0]["workflow_id"] == broken["id"]
    assert "not_a_real_node" in body["unrunnable"][0]["reason"]


def test_a_lab_event_carries_values_into_the_conditionals(
    client, fake_db, auth_header
):
    patient = _patient(fake_db)
    _workflow(
        fake_db,
        *_threshold_graph(
            test_name="HbA1c", operator="greater_than", threshold="7", abnormal_branch="none"
        ),
    )

    response = client.post(
        "/api/lab-event",
        json={
            "trigger_type": "lab_results_received",
            "patient_id": patient["id"],
            "metadata": {"results": {"HbA1c": 8.8}},
        },
        headers=auth_header(ALICE),
    )

    steps = response.json()["runs"][0]["execution_log"]
    threshold = next(s for s in steps if s["node_type"] == "check_result_values")
    assert threshold["branch"] == "true"
    assert "8.8" in threshold["message"]


# ---------------------------------------------------------------------------
# Audit and provenance
# ---------------------------------------------------------------------------


def test_a_run_is_audited_without_recording_clinical_values(
    client, fake_db, auth_header
):
    """The trail records that an access happened. Duplicating what was accessed
    into it puts PHI in every log export."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db, *_threshold_graph(test_name="HbA1c", operator="greater_than", threshold="7")
    )

    _run(
        client,
        auth_header,
        workflow["id"],
        patient["id"],
        metadata={"results": {"hba1c": 8.2}},
    )

    entry = next(
        row for row in fake_db.store["audit_log"] if row["action"] == "workflow.execute"
    )
    assert entry["doctor_id"] == ALICE
    assert entry["patient_id"] == patient["id"]
    assert entry["metadata"]["graph_fingerprint"]
    assert "8.2" not in json.dumps(entry["metadata"])


def test_a_referral_a_workflow_raises_is_attributed_to_its_own_tenant(
    client, fake_db, auth_header
):
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "abnormal_result_detected"),
            _node("r1", "create_referral", specialty="Endocrinology", reason="Raised HbA1c", urgency="urgent"),
        ],
        [_edge("t1", "r1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    assert _step_for(response, "create_referral")["status"] == "ok"
    referral = fake_db.store["referrals"][0]
    assert referral["referring_doctor_id"] == ALICE
    assert referral["urgency"] == "urgent"


def test_an_urgency_the_database_would_refuse_blocks_first(
    client, fake_db, auth_header
):
    """A CHECK constraint violation is a 500 naming a constraint, which tells the
    workflow's author nothing they can act on."""
    patient = _patient(fake_db)
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "follow_up_due"),
            _node("r1", "create_referral", specialty="Cardiology", reason="x", urgency="whenever"),
        ],
        [_edge("t1", "r1")],
    )

    response = _run(client, auth_header, workflow["id"], patient["id"])

    step = _step_for(response, "create_referral")
    assert step["status"] == "blocked"
    assert "urgency" in step["message"]
    assert fake_db.store.get("referrals", []) == []


def test_updating_a_patient_record_appends_notes_rather_than_replacing_them(
    client, fake_db, auth_header
):
    patient = _patient(fake_db, notes="Existing clinical note.", risk_level="low")
    workflow = _workflow(
        fake_db,
        [
            _node("t1", "abnormal_result_detected"),
            _node("u1", "update_patient_record", risk_level="high", notes="Flagged by workflow."),
        ],
        [_edge("t1", "u1")],
    )

    _run(client, auth_header, workflow["id"], patient["id"])

    stored = next(r for r in fake_db.store["patients"] if r["id"] == patient["id"])
    assert stored["risk_level"] == "high"
    assert stored["notes"].startswith("Existing clinical note.")
    assert "Flagged by workflow." in stored["notes"]


def test_every_catalogued_node_type_has_a_handler():
    """The registry check runs at import; this states the property out loud so a
    node type added to the catalogue without a handler fails a test as well as
    the boot."""
    from app.engine.catalogue import ALL_NODE_TYPES

    assert set(engine_nodes.HANDLERS) == set(ALL_NODE_TYPES)
