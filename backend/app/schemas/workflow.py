"""Workflow request/response models.

`nodes` and `edges` are the React Flow graph the builder produces, stored as
JSONB and handed back unchanged. They are deliberately not modelled further
here: the builder owns that shape, it changes whenever a node type is added,
and a Pydantic model tracking it would reject graphs the frontend considers
valid without protecting anything — the graph is the caller's own data, not a
security boundary.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import READ_CONFIG, REQUEST_CONFIG, blank_to_none

# Must stay in step with the CHECK constraint on workflows.status. A value
# that passes here and fails there is a 500 rather than a 422.
WorkflowStatus = Literal["DRAFT", "ENABLED", "ARCHIVED"]


class WorkflowCreate(BaseModel):
    model_config = REQUEST_CONFIG

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    status: WorkflowStatus = "DRAFT"

    # Read by the call engine to personalise what the voice agent says. Free
    # text and the doctor's own display name, not an identity claim — the
    # tenant key is doctor_id, which no payload can set.
    doctor_name: str | None = Field(default=None, max_length=200)

    nodes: list[Any] = []
    edges: list[Any] = []

    _normalise = field_validator(
        "description", "category", "doctor_name", mode="before"
    )(blank_to_none)


class WorkflowUpdate(BaseModel):
    model_config = REQUEST_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    status: WorkflowStatus | None = None
    doctor_name: str | None = Field(default=None, max_length=200)
    nodes: list[Any] | None = None
    edges: list[Any] | None = None

    _normalise = field_validator(
        "description", "category", "doctor_name", mode="before"
    )(blank_to_none)


class WorkflowRead(BaseModel):
    model_config = READ_CONFIG

    id: str
    doctor_id: str
    name: str
    description: str | None = None
    category: str | None = None
    status: str = "DRAFT"
    doctor_name: str | None = None
    nodes: list[Any] = []
    edges: list[Any] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
