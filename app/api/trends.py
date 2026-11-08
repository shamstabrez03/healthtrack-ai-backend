"""Trends API routes — longitudinal health data."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta
from app.database.session import get_db
from app.database.repositories import PatientRepository, ObservationRepository
from app.schemas.observations import TrendResponse, AvailableTestsResponse
from app.api.auth import get_current_user
from app.api.dashboard import _compute_trend
from app.database.models import User

router = APIRouter(prefix="/api/trends", tags=["trends"])


@router.get("/available-tests", response_model=AvailableTestsResponse)
def get_available_tests(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of tests available for trend analysis."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    tests = ObservationRepository.get_available_tests(db, patient_id)
    return AvailableTestsResponse(tests=tests)


@router.get("/{test_name}", response_model=TrendResponse)
def get_trend(
    test_name: str,
    patient_id: str,
    period: Optional[str] = Query(None, pattern="^(3m|6m|1y|3y|all)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get trend data for a specific test."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    trend = _compute_trend(db, patient_id, test_name)
    if not trend or not trend.data_points:
        raise HTTPException(status_code=404, detail="No trend data available for this test")

    # Apply time filter if specified
    if period and period != "all":
        today = date.today()
        period_map = {
            "3m": timedelta(days=90),
            "6m": timedelta(days=180),
            "1y": timedelta(days=365),
            "3y": timedelta(days=1095),
        }
        cutoff = today - period_map.get(period, timedelta(days=365))
        trend.data_points = [dp for dp in trend.data_points if dp.date >= cutoff]

    return trend
