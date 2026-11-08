"""SQLAlchemy ORM models for the medical report system."""

import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, DateTime, Date,
    ForeignKey, Enum as SAEnum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.session import Base
import enum


def generate_uuid():
    return str(uuid.uuid4())


# --- Enums ---

class ReportStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


class ValueType(str, enum.Enum):
    NUMERIC = "numeric"
    TEXT = "text"
    QUALITATIVE = "qualitative"


class ObservationStatus(str, enum.Enum):
    WITHIN_RANGE = "within_range"
    NORMAL = "normal"
    ATTENTION = "attention"
    SIGNIFICANT = "significant"
    POTENTIALLY_URGENT = "potentially_urgent"
    UNKNOWN = "unknown"


# --- Models ---

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Encrypted Gemini API key (stored server-side)
    gemini_api_key_encrypted = Column(Text, nullable=True)
    gemini_model = Column(String(100), default="gemini-2.5-flash")

    # Relationships
    patients = relationship("Patient", back_populates="user", cascade="all, delete-orphan")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    relationship_type = Column(String(50), default="self")  # self, father, mother, spouse, child, other
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="patients")
    reports = relationship("Report", back_populates="patient", cascade="all, delete-orphan")
    observations = relationship("Observation", back_populates="patient", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_patients_user_id", "user_id"),
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)

    # File info
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=True)  # SHA-256
    original_filename = Column(String(255), nullable=False)

    # Report metadata
    report_type = Column(String(100), nullable=True)  # blood_test, xray, ultrasound, ecg, etc.
    report_date = Column(Date, nullable=True)  # Best clinical date
    collection_date = Column(Date, nullable=True)
    collection_time = Column(String(20), nullable=True)
    reported_date = Column(Date, nullable=True)
    generated_date = Column(Date, nullable=True)

    # Lab / Hospital
    laboratory = Column(String(255), nullable=True)
    lab_number = Column(String(100), nullable=True)
    referring_doctor = Column(String(255), nullable=True)

    # Patient info from report
    patient_name_on_report = Column(String(255), nullable=True)
    age_on_report = Column(String(50), nullable=True)
    gender_on_report = Column(String(20), nullable=True)

    # Processing
    status = Column(String(50), default=ReportStatus.UPLOADED.value)
    processing_message = Column(Text, nullable=True)
    total_pages = Column(Integer, nullable=True)

    # AI-generated summary
    summary = Column(Text, nullable=True)

    # Duplicate detection
    duplicate_of_id = Column(String, ForeignKey("reports.id", ondelete="SET NULL"), nullable=True)
    is_duplicate = Column(Boolean, default=False)

    # Timestamps
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="reports")
    observations = relationship("Observation", back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_reports_patient_id", "patient_id"),
        Index("ix_reports_report_date", "report_date"),
        Index("ix_reports_file_hash", "file_hash"),
        Index("ix_reports_status", "status"),
    )


class Observation(Base):
    __tablename__ = "observations"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)

    # Panel / Category
    panel = Column(String(200), nullable=True)

    # Test names
    test_name = Column(String(300), nullable=False)  # Original from report
    canonical_test_name = Column(String(200), nullable=True)  # Normalized

    # Values
    value_text = Column(String(200), nullable=True)  # Always store original text
    value_numeric = Column(Float, nullable=True)  # Parsed numeric if applicable
    value_type = Column(String(20), default=ValueType.NUMERIC.value)

    # Units
    unit = Column(String(50), nullable=True)  # Original unit
    normalized_value = Column(Float, nullable=True)
    normalized_unit = Column(String(50), nullable=True)

    # Reference range
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    reference_text = Column(String(200), nullable=True)  # Original ref text from report

    # Status
    status = Column(String(30), default=ObservationStatus.UNKNOWN.value)
    interpretation = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Traceability
    source_page = Column(Integer, nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    needs_review = Column(Boolean, default=False)

    # Clinical date (inherited from report for easier querying)
    report_date = Column(Date, nullable=True)

    __table_args__ = (
        Index("ix_observations_report_id", "report_id"),
        Index("ix_observations_patient_id", "patient_id"),
        Index("ix_observations_canonical_test", "canonical_test_name"),
        Index("ix_observations_patient_test", "patient_id", "canonical_test_name"),
        Index("ix_observations_report_date", "report_date"),
    )

    # Relationships
    report = relationship("Report", back_populates="observations")
    patient = relationship("Patient", back_populates="observations")


from pgvector.sqlalchemy import Vector


class ReportEmbedding(Base):
    __tablename__ = "report_embeddings"

    id = Column(String, primary_key=True, default=generate_uuid)
    report_id = Column(String, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)

    chunk_text = Column(Text, nullable=False)
    chunk_type = Column(String(50), default="page")  # "page" or "panel_summary"
    page_number = Column(Integer, nullable=True)
    panel = Column(String(200), nullable=True)

    report_type = Column(String(100), nullable=True)
    report_date = Column(String(50), nullable=True)
    laboratory = Column(String(255), nullable=True)

    embedding = Column(Vector(768), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_embeddings_patient_id", "patient_id"),
        Index("ix_embeddings_report_id", "report_id"),
    )

    report = relationship("Report")
    patient = relationship("Patient")
