"""Patient CRUD.

This is the reference vertical slice. Every resource ported back into this
backend should follow the shape here:

  * the URL matches what frontend/services/api.ts already calls
  * the handler takes TenantDep and never touches the Supabase client directly
  * any client-supplied doctor_id is ignored in favour of the token subject
  * "not yours" and "not found" both surface as 404

Handlers are sync `def` because the Supabase client is blocking; FastAPI runs
them in a threadpool rather than stalling the event loop.
"""
from fastapi import APIRouter, Response, status

from app.api.deps import TenantDep
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientRead])
def list_patients(scope: TenantDep) -> list[dict]:
    """List the caller's patients.

    The frontend still sends ?doctor_id=... — it is not declared, not read, and
    has no effect. Scoping comes from the token.
    """
    return scope.list_owned("patients")


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, scope: TenantDep) -> dict:
    return scope.insert_owned("patients", payload.model_dump(mode="json"))


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: str, scope: TenantDep) -> dict:
    return scope.get_owned("patients", patient_id)


@router.put("/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: str, payload: PatientUpdate, scope: TenantDep) -> dict:
    # exclude_unset so an omitted field is left alone rather than nulled.
    return scope.update_owned(
        "patients", patient_id, payload.model_dump(mode="json", exclude_unset=True)
    )


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: str, scope: TenantDep) -> Response:
    scope.delete_owned("patients", patient_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
