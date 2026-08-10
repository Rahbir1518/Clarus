"""Running a workflow — request/response models.

The same asymmetry as schemas/call.py: a caller says *which* workflow and *which*
patient, and never what the resulting call should say. Everything spoken is
assembled server-side from the workflow's own nodes, through the fixed
vocabulary in `app.engine.policy`.

`metadata` is the exception, and it is worth being precise about what it is: the
body of the event that fired the trigger — lab values, a flag saying the result
was abnormal — used to evaluate conditionals. It never reaches the voice agent.
Nothing in it is spoken, which is why free-form JSON is safe here and is not safe
in a field like `appointment_reason`.
"""
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.engine.catalogue import TRIGGER_TYPES
from app.schemas.common import READ_CONFIG, REQUEST_CONFIG


class ExecuteWorkflow(BaseModel):
    """Run one named workflow against one patient."""

    model_config = REQUEST_CONFIG

    patient_id: str = Field(..., min_length=1)

    # Which trigger the run starts from. Optional only because a workflow with
    # exactly one trigger has no ambiguity to resolve; with several, the engine
    # requires it rather than picking. REBUILD_CHECKLIST.md records this
    # parameter being accepted, documented and ignored in the previous system.
    trigger_node_type: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trigger_node_type")
    @classmethod
    def _known_trigger(cls, value: str | None) -> str | None:
        if value and value not in TRIGGER_TYPES:
            raise ValueError(
                f"unknown trigger type {value!r}; expected one of "
                + ", ".join(sorted(TRIGGER_TYPES))
            )
        return value


class LabEvent(BaseModel):
    """Something happened to a patient. Fan it out to whatever listens.

    The frontend also sends `doctor_id`; `extra="ignore"` drops it, and the
    tenant comes from the verified token. See schemas/common.py.
    """

    model_config = REQUEST_CONFIG

    trigger_type: str = Field(..., min_length=1)
    patient_id: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trigger_type")
    @classmethod
    def _known_trigger(cls, value: str) -> str:
        if value not in TRIGGER_TYPES:
            # A 422 naming the field, rather than a 200 saying nothing matched.
            # "No workflow listens for this" and "that trigger does not exist"
            # look identical from the outside and need different fixes.
            raise ValueError(
                f"unknown trigger type {value!r}; expected one of "
                + ", ".join(sorted(TRIGGER_TYPES))
            )
        return value


class RunRead(BaseModel):
    """What one execution did.

    `execution_log` is handed back as stored. Its shape is documented in
    `app/engine/steps.py`, and the run panel in
    frontend/components/workflow/WorkflowBuilder.tsx reads `status`, `label`,
    `node_type` and `message` off each step.
    """

    model_config = READ_CONFIG

    call_log_id: str
    # completed | parked | failed | blocked. `parked` means a call is in flight
    # and the rest of the run continues when the post-call webhook arrives.
    status: str
    execution_log: list[dict[str, Any]] = []
    workflow_id: str | None = None


class UnrunnableWorkflow(BaseModel):
    """An enabled workflow that listens for this trigger but cannot be walked.

    Reported rather than swallowed. An enabled workflow that silently never
    fires because its graph is malformed is the kind of thing nobody discovers
    until they ask why a patient was not called.
    """

    model_config = READ_CONFIG

    workflow_id: str
    name: str | None = None
    reason: str


class LabEventResult(BaseModel):
    model_config = READ_CONFIG

    trigger_type: str
    patient_id: str
    matched: int
    runs: list[RunRead] = []
    unrunnable: list[UnrunnableWorkflow] = []
