"""Pydantic schemas for observations."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from app.schemas.reports import ReportResponse


class ObservationResponse(BaseModel):
    id: str
    report_id: str
    panel: Optional[str] = None
    test_name: str
    canonical_test_name: Optional[str] = None
    value_text: Optional[str] = None
    value_numeric: Optional[float] = None
    value_type: str
    unit: Optional[str] = None
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_text: Optional[str] = None
    status: str
    interpretation: Optional[str] = None
    notes: Optional[str] = None
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    confidence: float = 1.0
    needs_review: bool = False
    report_date: Optional[date] = None

    model_config = {"from_attributes": True}


class ObservationListResponse(BaseModel):
    observations: List[ObservationResponse]
    total: int


class TrendPoint(BaseModel):
    """A single data point in a trend series."""
    date: date
    value: float
    unit: Optional[str] = None
    status: str
    report_id: str
    report_type: Optional[str] = None


class TrendResponse(BaseModel):
    """Trend data for a single test."""
    test_name: str
    canonical_test_name: str
    unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_text: Optional[str] = None
    data_points: List[TrendPoint]
    first_value: Optional[float] = None
    latest_value: Optional[float] = None
    previous_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None
    absolute_change: Optional[float] = None
    percentage_change: Optional[float] = None
    direction: Optional[str] = None  # increasing, decreasing, stable
    latest_status: Optional[str] = None


class AvailableTestsResponse(BaseModel):
    tests: List[dict]  # [{canonical_name, display_name, unit, latest_value, latest_status, data_point_count}]


class DashboardResponse(BaseModel):
    """Dashboard overview data."""
    patient_id: str
    patient_name: str
    report_count: int
    tracked_test_count: int
    reports_this_year: int
    attention_count: int
    latest_reports: List[ReportResponse]
    attention_items: List[ObservationResponse]
    key_trends: List[TrendResponse]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    patient_id: str
    report_id: Optional[str] = None  # If scoped to a specific report


class ChatResponse(BaseModel):
    response: str
    sources: List[dict] = []  # [{report_id, report_type, report_date, page_number, text}]
    trend_data: Optional[dict] = None
    disclaimer: Optional[str] = None


DashboardResponse.model_rebuild()
