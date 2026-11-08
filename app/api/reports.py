"""Report API routes — upload, list, get, delete."""

import hashlib
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.database.repositories import ReportRepository, PatientRepository, ObservationRepository
from app.schemas.reports import ReportResponse, ReportListResponse, ReportUploadResponse
from app.schemas.observations import ObservationResponse, ObservationListResponse
from app.api.auth import get_current_user
from app.database.models import User, ReportStatus
from app.config import settings
from pathlib import Path

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _report_to_response(db: Session, report) -> ReportResponse:
    obs_count = ObservationRepository.get_observation_count_for_report(db, report.id)
    abn_count = ObservationRepository.get_abnormal_count_for_report(db, report.id)
    return ReportResponse(
        id=report.id,
        patient_id=report.patient_id,
        original_filename=report.original_filename,
        report_type=report.report_type,
        report_date=report.report_date,
        collection_date=report.collection_date,
        reported_date=report.reported_date,
        laboratory=report.laboratory,
        lab_number=report.lab_number,
        referring_doctor=report.referring_doctor,
        patient_name_on_report=report.patient_name_on_report,
        age_on_report=report.age_on_report,
        gender_on_report=report.gender_on_report,
        status=report.status,
        processing_message=report.processing_message,
        total_pages=report.total_pages,
        summary=report.summary,
        is_duplicate=report.is_duplicate or False,
        upload_timestamp=report.upload_timestamp,
        processed_at=report.processed_at,
        observation_count=obs_count,
        abnormal_count=abn_count,
    )


@router.post("/upload", response_model=ReportUploadResponse)
async def upload_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a medical report PDF for processing."""
    # Validate patient belongs to user
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(allowed_extensions)}")

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Compute file hash
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicates
    duplicate = ReportRepository.find_duplicate(db, patient_id, file_hash)
    if duplicate:
        # Check if the duplicate was failed or interrupted with 0 observations
        obs_count = ObservationRepository.get_observation_count_for_report(db, duplicate.id)
        if duplicate.status == ReportStatus.FAILED.value or (
            duplicate.status in [ReportStatus.UPLOADED.value, ReportStatus.PROCESSING.value, ReportStatus.EXTRACTING.value]
            and obs_count == 0
        ):
            # Clean up old failed/stale draft and reprocess cleanly
            try:
                from app.rag.vector_service import vector_service
                vector_service.delete_report_data(duplicate.id, db=db)
            except Exception:
                pass
            try:
                old_file = Path(duplicate.file_path)
                if old_file.exists():
                    old_file.unlink()
            except Exception:
                pass
            ReportRepository.delete(db, duplicate.id, patient_id)
        else:
            return ReportUploadResponse(
                id=duplicate.id,
                status="duplicate",
                message="This report has already been uploaded",
                is_duplicate=True,
                duplicate_of_id=duplicate.id,
            )

    # Save file
    settings.ensure_directories()
    upload_dir = Path(settings.UPLOAD_DIR) / patient_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{file_hash}{file_ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # Create report record
    report = ReportRepository.create(
        db,
        patient_id=patient_id,
        file_path=str(file_path),
        original_filename=file.filename,
        file_hash=file_hash,
    )

    # Process report in background
    background_tasks.add_task(process_report_task, report.id, str(file_path), patient_id, current_user.id)

    return ReportUploadResponse(
        id=report.id,
        status=report.status,
        message="Report uploaded successfully. Processing will begin shortly.",
    )


def process_report_task(report_id: str, file_path: str, patient_id: str, user_id: str):
    """Background task to process an uploaded report."""
    from app.database.session import SessionLocal
    db = SessionLocal()
    try:
        from app.ingestion.report_processor import ReportProcessor
        processor = ReportProcessor(db, user_id)
        processor.process(report_id, file_path, patient_id)
    except Exception as e:
        ReportRepository.update_status(db, report_id, ReportStatus.FAILED.value, str(e))
    finally:
        db.close()


@router.post("/{report_id}/retry", response_model=ReportUploadResponse)
def retry_report(
    report_id: str,
    patient_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry processing a failed or incomplete report."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    report = ReportRepository.get_by_id(db, report_id, patient_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    file_path = Path(report.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Original file is not cached on server. Please upload the report again."
        )

    # Purge any partial vectors and observations before re-running
    try:
        from app.rag.vector_service import vector_service
        vector_service.delete_report_data(report.id, db=db)
    except Exception:
        pass

    try:
        from app.database.models import Observation
        db.query(Observation).filter(Observation.report_id == report_id).delete()
        db.commit()
    except Exception:
        db.rollback()

    ReportRepository.update_status(db, report_id, ReportStatus.PROCESSING.value, "Retrying processing...")
    background_tasks.add_task(process_report_task, report.id, str(file_path), patient_id, current_user.id)

    return ReportUploadResponse(
        id=report.id,
        status="processing",
        message="Report re-processing initiated.",
    )


@router.get("", response_model=ReportListResponse)
def list_reports(
    patient_id: str,
    report_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all reports for a patient."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    reports = ReportRepository.get_all_for_patient(db, patient_id, report_type, skip, limit)
    total = ReportRepository.get_count_for_patient(db, patient_id)
    return ReportListResponse(
        reports=[_report_to_response(db, r) for r in reports],
        total=total,
    )


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single report by ID."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    report = ReportRepository.get_by_id(db, report_id, patient_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_response(db, report)


@router.get("/{report_id}/observations", response_model=ObservationListResponse)
def get_report_observations(
    report_id: str,
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all observations for a specific report."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    observations = ObservationRepository.get_for_report(db, report_id, patient_id)
    return ObservationListResponse(
        observations=[ObservationResponse.model_validate(o) for o in observations],
        total=len(observations),
    )


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a report and ALL associated data (file, observations, ChromaDB)."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    report = ReportRepository.get_by_id(db, report_id, patient_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 1. Delete Vector DB data
    try:
        from app.rag.vector_service import vector_service
        vector_service.delete_report_data(report_id, db=db)
    except Exception:
        pass

    # 2. Delete the physical file
    try:
        file_path = Path(report.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass

    # 3. Delete DB records (cascades to observations)
    ReportRepository.delete(db, report_id, patient_id)

    return {"message": "Report and all associated data deleted successfully"}
