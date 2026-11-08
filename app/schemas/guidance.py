"""Pydantic schemas for AI Health Guidance and Urgent Alerts."""

from pydantic import BaseModel, Field
from typing import Optional, List


class UrgentAlertItem(BaseModel):
    test_name: str
    observed_value: str
    reference_interval: Optional[str] = None
    reason: str
    severity: str = "significant"  # "urgent" | "significant"


class UrgentAlert(BaseModel):
    has_urgent_findings: bool = False
    title: str = "Urgent Medical Attention Recommended"
    summary: str
    alert_items: List[UrgentAlertItem] = []
    recommendation: str = "We strongly advise scheduling an in-person clinical evaluation with a qualified physician promptly to assess these laboratory values. Do not start, stop, or alter any medications on your own."


class HealthGuidance(BaseModel):
    report_id: Optional[str] = None
    report_type: Optional[str] = None
    report_date: Optional[str] = None
    urgent_alert: Optional[UrgentAlert] = None
    general_summary: str
    dos: List[str] = []
    donts: List[str] = []
    diet_suggestions: List[str] = []
    lifestyle_suggestions: List[str] = []
    doctor_questions: List[str] = []
    disclaimer: str = (
        "Educational guidance only. These lifestyle, dietary, and observational suggestions "
        "do not constitute a medical diagnosis, prescription, or clinical treatment plan. "
        "Always consult your doctor or healthcare specialist."
    )
