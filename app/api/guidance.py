"""Guidance API routes — report health guidance, Do's & Don'ts, and urgent doctor alerts."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.database.repositories import PatientRepository, ReportRepository
from app.schemas.guidance import HealthGuidance
from app.api.auth import get_current_user
from app.database.models import User
from app.guidance.health_advisor import analyze_report_guidance

router = APIRouter(prefix="/api/guidance", tags=["guidance"])


@router.get("/latest", response_model=HealthGuidance)
def get_latest_guidance(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get personalized health guidance and urgent alerts for patient's latest report."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    guidance = analyze_report_guidance(
        db=db,
        patient_id=patient_id,
        user_id=current_user.id,
        report_id=None
    )
    return guidance


@router.get("/report/{report_id}", response_model=HealthGuidance)
def get_report_guidance(
    report_id: str,
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get personalized health guidance and urgent alerts for a specific report."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    report = ReportRepository.get_by_id(db, report_id, patient_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    guidance = analyze_report_guidance(
        db=db,
        patient_id=patient_id,
        user_id=current_user.id,
        report_id=report_id
    )
    return guidance
