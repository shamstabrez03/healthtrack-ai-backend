"""Pydantic schemas for reports."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


class ReportResponse(BaseModel):
    id: str
    patient_id: str
    original_filename: str
    report_type: Optional[str] = None
    report_date: Optional[date] = None
    collection_date: Optional[date] = None
    reported_date: Optional[date] = None
    laboratory: Optional[str] = None
    lab_number: Optional[str] = None
    referring_doctor: Optional[str] = None
    patient_name_on_report: Optional[str] = None
    age_on_report: Optional[str] = None
    gender_on_report: Optional[str] = None
    status: str
    processing_message: Optional[str] = None
    total_pages: Optional[int] = None
    summary: Optional[str] = None
    is_duplicate: bool = False
    upload_timestamp: datetime
    processed_at: Optional[datetime] = None
    observation_count: int = 0
    abnormal_count: int = 0

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    reports: List[ReportResponse]
    total: int


class ReportUploadResponse(BaseModel):
    id: str
    status: str
    message: str
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
