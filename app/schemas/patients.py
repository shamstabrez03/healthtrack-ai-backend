"""Pydantic schemas for patients/family members."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class PatientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    relationship_type: str = Field(default="self", max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None


class PatientUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[str] = Field(None, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None


class PatientResponse(BaseModel):
    id: str
    name: str
    relationship_type: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    created_at: datetime
    report_count: int = 0
    last_report_date: Optional[date] = None

    model_config = {"from_attributes": True}
