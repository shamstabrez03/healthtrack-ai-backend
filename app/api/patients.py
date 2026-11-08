"""Patient/Family API routes — CRUD for family members."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.database.repositories import PatientRepository
from app.schemas.patients import PatientCreate, PatientUpdate, PatientResponse
from app.api.auth import get_current_user
from app.database.models import User

router = APIRouter(prefix="/api/family", tags=["family"])


def _enrich_patient(db: Session, patient) -> PatientResponse:
    """Add report_count and last_report_date to patient response."""
    return PatientResponse(
        id=patient.id,
        name=patient.name,
        relationship_type=patient.relationship_type,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        created_at=patient.created_at,
        report_count=PatientRepository.get_report_count(db, patient.id),
        last_report_date=PatientRepository.get_last_report_date(db, patient.id),
    )


@router.get("", response_model=List[PatientResponse])
def list_family(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all family members/patient profiles for the current user."""
    patients = PatientRepository.get_all_for_user(db, current_user.id)
    return [_enrich_patient(db, p) for p in patients]


@router.post("", response_model=PatientResponse, status_code=201)
def create_family_member(
    data: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new family member profile."""
    patient = PatientRepository.create(
        db,
        user_id=current_user.id,
        name=data.name,
        relationship_type=data.relationship_type,
        date_of_birth=data.date_of_birth,
        gender=data.gender,
    )
    return _enrich_patient(db, patient)


@router.put("/{patient_id}", response_model=PatientResponse)
def update_family_member(
    patient_id: str,
    data: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a family member profile."""
    update_data = data.model_dump(exclude_none=True)
    patient = PatientRepository.update(db, patient_id, current_user.id, **update_data)
    if not patient:
        raise HTTPException(status_code=404, detail="Family member not found")
    return _enrich_patient(db, patient)


@router.delete("/{patient_id}")
def delete_family_member(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a family member and ALL their data (reports, observations, ChromaDB)."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Family member not found")

    if patient.relationship_type == "self":
        raise HTTPException(status_code=400, detail="Cannot delete your own profile")

    # Clean up Vector DB data for this patient
    try:
        from app.rag.vector_service import vector_service
        vector_service.delete_patient_data(patient_id, db=db)
    except Exception:
        pass

    # Delete patient (cascades to reports and observations via FK)
    PatientRepository.delete(db, patient_id, current_user.id)
    return {"message": "Family member and all associated data deleted"}
