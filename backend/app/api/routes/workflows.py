"""Workflow CRUD.

Same shape as routes/patients.py. One thing here is not shared with it: a
workflow has no `deleted_at`, so DELETE removes the row outright. That is the
schema's decision, not this module's — a workflow is retired by moving it to
status 'ARCHIVED', which keeps the call logs and reports it produced pointing
at something that still exists. Deleting one that has run is a real loss of
history, and the UI should be archiving instead.
"""
from fastapi import APIRouter, Response, status

from app.api.deps import TenantDep
from app.schemas.workflow import WorkflowCreate, WorkflowRead, WorkflowUpdate

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowRead])
def list_workflows(scope: TenantDep, status: str | None = None) -> list[dict]:
    """List the caller's workflows.

    The frontend also sends ?doctor_id=... — undeclared, unread, no effect.
    """
    return scope.list_owned("workflows", filters={"status": status})


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, scope: TenantDep) -> dict:
    return scope.insert_owned("workflows", payload.model_dump(mode="json"))


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: str, scope: TenantDep) -> dict:
    return scope.get_owned("workflows", workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: str, payload: WorkflowUpdate, scope: TenantDep
) -> dict:
    # exclude_unset so an omitted field is left alone rather than nulled. The
    # builder saves the whole graph, but the triggers page toggles status on
    # its own and must not blank the nodes it never loaded.
    return scope.update_owned(
        "workflows", workflow_id, payload.model_dump(mode="json", exclude_unset=True)
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str, scope: TenantDep) -> Response:
    scope.delete_owned("workflows", workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
