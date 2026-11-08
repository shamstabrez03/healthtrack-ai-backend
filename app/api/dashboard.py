"""Dashboard API route — aggregated health overview."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.database.repositories import (
    ReportRepository, ObservationRepository, PatientRepository
)
from app.schemas.observations import DashboardResponse, ObservationResponse, TrendResponse, TrendPoint
from app.schemas.reports import ReportResponse
from app.api.auth import get_current_user
from app.api.reports import _report_to_response
from app.database.models import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregated dashboard data for a patient."""
    patient = PatientRepository.get_by_id(db, patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Counts
    report_count = ReportRepository.get_count_for_patient(db, patient_id)
    tracked_tests = ObservationRepository.get_tracked_test_count(db, patient_id)
    reports_this_year = ReportRepository.get_reports_this_year(db, patient_id)
    attention_count = ObservationRepository.get_attention_count(db, patient_id)

    # Latest reports
    latest_reports = ReportRepository.get_latest_reports(db, patient_id, limit=5)
    latest_report_responses = [_report_to_response(db, r) for r in latest_reports]

    # Attention items
    attention_obs = ObservationRepository.get_attention_items(db, patient_id, limit=10)
    attention_responses = [ObservationResponse.model_validate(o) for o in attention_obs]

    # Key trends (get the most commonly tracked tests)
    key_trend_tests = _get_key_trend_tests(db, patient_id)
    key_trends = []
    for test_info in key_trend_tests[:6]:
        trend = _compute_trend(db, patient_id, test_info["canonical_name"])
        if trend and trend.data_points:
            key_trends.append(trend)

    return DashboardResponse(
        patient_id=patient_id,
        patient_name=patient.name,
        report_count=report_count,
        tracked_test_count=tracked_tests,
        reports_this_year=reports_this_year,
        attention_count=attention_count,
        latest_reports=latest_report_responses,
        attention_items=attention_responses,
        key_trends=key_trends,
    )


def _get_key_trend_tests(db: Session, patient_id: str):
    """Get the most important tests to show on dashboard."""
    # Priority tests for dashboard display
    priority_tests = [
        "LDL Cholesterol", "HDL Cholesterol", "Total Cholesterol", "Triglycerides",
        "Hemoglobin", "TSH", "Fasting Glucose", "HbA1c",
        "ALT", "AST", "Creatinine", "Uric Acid",
    ]

    available = ObservationRepository.get_available_tests(db, patient_id)
    available_map = {t["canonical_name"]: t for t in available}

    # Return priority tests first, then others
    result = []
    for test_name in priority_tests:
        if test_name in available_map:
            result.append(available_map[test_name])

    for test in available:
        if test["canonical_name"] not in [r["canonical_name"] for r in result]:
            result.append(test)

    return result


def _compute_trend(db: Session, patient_id: str, canonical_test_name: str) -> TrendResponse:
    """Compute trend data for a specific test — all calculations in Python."""
    observations = ObservationRepository.get_trend_data(db, patient_id, canonical_test_name)

    if not observations:
        return None

    data_points = []
    for obs in observations:
        if obs.report_date and obs.value_numeric is not None:
            data_points.append(TrendPoint(
                date=obs.report_date,
                value=obs.value_numeric,
                unit=obs.unit,
                status=obs.status or "unknown",
                report_id=obs.report_id,
                report_type=None,
            ))

    if not data_points:
        return None

    values = [dp.value for dp in data_points]
    first_value = values[0] if values else None
    latest_value = values[-1] if values else None
    previous_value = values[-2] if len(values) >= 2 else None

    # Calculate changes in Python (not LLM)
    absolute_change = None
    percentage_change = None
    direction = "stable"

    if previous_value is not None and latest_value is not None:
        absolute_change = round(latest_value - previous_value, 4)
        if previous_value != 0:
            percentage_change = round((absolute_change / abs(previous_value)) * 100, 2)
        if absolute_change > 0:
            direction = "increasing"
        elif absolute_change < 0:
            direction = "decreasing"

    ref_low = observations[-1].reference_low if observations else None
    ref_high = observations[-1].reference_high if observations else None
    ref_text = observations[-1].reference_text if observations else None

    return TrendResponse(
        test_name=observations[-1].test_name,
        canonical_test_name=canonical_test_name,
        unit=observations[-1].unit,
        reference_low=ref_low,
        reference_high=ref_high,
        reference_text=ref_text,
        data_points=data_points,
        first_value=first_value,
        latest_value=latest_value,
        previous_value=previous_value,
        min_value=round(min(values), 4) if values else None,
        max_value=round(max(values), 4) if values else None,
        avg_value=round(sum(values) / len(values), 4) if values else None,
        absolute_change=absolute_change,
        percentage_change=percentage_change,
        direction=direction,
        latest_status=observations[-1].status if observations else None,
    )
