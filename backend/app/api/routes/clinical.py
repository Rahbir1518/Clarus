"""Conditions and medications, both nested under a patient.

The nesting is the access control, not decoration. Every handler here goes
through TenantScope's `*_for_patient` methods, which resolve the parent patient
against the caller before touching the child table — these tables carry no
doctor_id of their own, so ownership has nowhere else to come from.

That resolution is also why "not yours" and "not found" are the same 404 on
both segments of the URL: a caller who guessed another practice's patient id
learns nothing from the response about whether it exists.
"""
from fastapi import APIRouter, Response, status

from app.api.deps import TenantDep
from app.schemas.clinical import (
    ConditionCreate,
    ConditionRead,
    ConditionUpdate,
    MedicationCreate,
    MedicationRead,
    MedicationUpdate,
)

conditions_router = APIRouter(
    prefix="/patients/{patient_id}/conditions", tags=["conditions"]
)
medications_router = APIRouter(
    prefix="/patients/{patient_id}/medications", tags=["medications"]
)


# -- conditions -------------------------------------------------------------


@conditions_router.get("", response_model=list[ConditionRead])
def list_conditions(patient_id: str, scope: TenantDep) -> list[dict]:
    return scope.list_for_patient("patient_conditions", patient_id)


@conditions_router.post(
    "", response_model=ConditionRead, status_code=status.HTTP_201_CREATED
)
def create_condition(
    patient_id: str, payload: ConditionCreate, scope: TenantDep
) -> dict:
    return scope.insert_for_patient(
        "patient_conditions", patient_id, payload.model_dump(mode="json")
    )


@conditions_router.put("/{condition_id}", response_model=ConditionRead)
def update_condition(
    patient_id: str, condition_id: str, payload: ConditionUpdate, scope: TenantDep
) -> dict:
    return scope.update_for_patient(
        "patient_conditions",
        patient_id,
        condition_id,
        payload.model_dump(mode="json", exclude_unset=True),
    )


@conditions_router.delete("/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_condition(patient_id: str, condition_id: str, scope: TenantDep) -> Response:
    scope.delete_for_patient("patient_conditions", patient_id, condition_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- medications ------------------------------------------------------------


@medications_router.get("", response_model=list[MedicationRead])
def list_medications(patient_id: str, scope: TenantDep) -> list[dict]:
    return scope.list_for_patient("patient_medications", patient_id)


@medications_router.post(
    "", response_model=MedicationRead, status_code=status.HTTP_201_CREATED
)
def create_medication(
    patient_id: str, payload: MedicationCreate, scope: TenantDep
) -> dict:
    return scope.insert_for_patient(
        "patient_medications", patient_id, payload.model_dump(mode="json")
    )


@medications_router.put("/{medication_id}", response_model=MedicationRead)
def update_medication(
    patient_id: str, medication_id: str, payload: MedicationUpdate, scope: TenantDep
) -> dict:
    return scope.update_for_patient(
        "patient_medications",
        patient_id,
        medication_id,
        payload.model_dump(mode="json", exclude_unset=True),
    )


@medications_router.delete("/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(
    patient_id: str, medication_id: str, scope: TenantDep
) -> Response:
    scope.delete_for_patient("patient_medications", patient_id, medication_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
