"""
Report processing pipeline orchestrator.

PDF → Extract text → Extract data via Gemini → Validate → Normalize → Persist → ChromaDB index
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.models import ReportStatus
from app.database.repositories import ReportRepository, ObservationRepository, UserRepository
from app.ingestion.pdf_parser import extract_pdf_text, get_full_text
from app.extraction.extractor import extract_report_data, classify_report_type
from app.extraction.validator import validate_observations, determine_status
from app.normalization.test_normalizer import normalize_test_name
from app.api.auth import decrypt_api_key

logger = logging.getLogger(__name__)


class ReportProcessor:
    """Orchestrates the full report processing pipeline."""

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        self._api_key = None
        self._model_name = "gemini-2.5-flash"
        self._load_user_config()

    def _load_user_config(self):
        """Load user's Gemini configuration."""
        user = UserRepository.get_by_id(self.db, self.user_id)
        if user and user.gemini_api_key_encrypted:
            self._api_key = decrypt_api_key(user.gemini_api_key_encrypted)
        if user and user.gemini_model:
            self._model_name = user.gemini_model

    def process(self, report_id: str, file_path: str, patient_id: str):
        """
        Run the full processing pipeline for an uploaded report.
        Updates status at each step.
        """
        try:
            # Step 1: Extract text
            self._update_status(report_id, ReportStatus.EXTRACTING.value, "Extracting text from document...")
            pages = extract_pdf_text(file_path)

            if not pages or not any(p.text.strip() for p in pages):
                self._update_status(report_id, ReportStatus.FAILED.value,
                                    "No text could be extracted from this document. It may be a scanned image.")
                return

            total_pages = len(pages)
            ReportRepository.update_metadata(self.db, report_id, total_pages=total_pages)

            full_text = get_full_text(pages)

            # Step 2: Check for API key
            if not self._api_key:
                self._update_status(report_id, ReportStatus.FAILED.value,
                                    "No Gemini API key configured. Please add your API key in Settings.")
                return

            # Step 3: Extract structured data using Gemini
            self._update_status(report_id, ReportStatus.PROCESSING.value, "Understanding report content...")
            extracted = extract_report_data(pages, self._api_key, self._model_name)

            # Step 4: Update report metadata
            patient_info = extracted.get("patient", {})
            report_info = extracted.get("report", {})

            metadata_update = {}
            if report_info.get("report_type"):
                metadata_update["report_type"] = report_info["report_type"]
            if report_info.get("laboratory"):
                metadata_update["laboratory"] = report_info["laboratory"]
            if report_info.get("lab_number"):
                metadata_update["lab_number"] = report_info["lab_number"]
            if report_info.get("referring_doctor") or patient_info.get("referring_doctor"):
                metadata_update["referring_doctor"] = report_info.get("referring_doctor") or patient_info.get("referring_doctor")

            # Dates
            if report_info.get("report_date"):
                metadata_update["report_date"] = self._parse_date(report_info["report_date"])
            if report_info.get("collection_date"):
                metadata_update["collection_date"] = self._parse_date(report_info["collection_date"])
            if report_info.get("reported_date"):
                metadata_update["reported_date"] = self._parse_date(report_info["reported_date"])
            if report_info.get("generated_date"):
                metadata_update["generated_date"] = self._parse_date(report_info["generated_date"])
            if report_info.get("collection_time"):
                metadata_update["collection_time"] = report_info["collection_time"]

            # Patient info from report
            if patient_info.get("name"):
                metadata_update["patient_name_on_report"] = patient_info["name"]
            if patient_info.get("age"):
                metadata_update["age_on_report"] = str(patient_info["age"])
            if patient_info.get("gender"):
                metadata_update["gender_on_report"] = patient_info["gender"]

            if metadata_update:
                ReportRepository.update_metadata(self.db, report_id, **metadata_update)

            # Step 5: Validate and normalize observations
            self._update_status(report_id, ReportStatus.VALIDATING.value, "Validating and normalizing results...")
            raw_observations = extracted.get("observations", [])

            if not raw_observations:
                self._update_status(report_id, ReportStatus.COMPLETED.value,
                                    "Report processed but no test observations were found.")
                return

            # Validate
            validated_obs = validate_observations(raw_observations)

            # Determine report date for observations
            report_date = metadata_update.get("report_date") or metadata_update.get("collection_date")

            # Build observation records
            obs_records = []
            for obs in validated_obs:
                canonical_name = normalize_test_name(obs.get("test_name", ""))
                status = determine_status(obs)

                obs_records.append({
                    "report_id": report_id,
                    "patient_id": patient_id,
                    "panel": obs.get("panel"),
                    "test_name": obs.get("test_name", "Unknown"),
                    "canonical_test_name": canonical_name,
                    "value_text": obs.get("value_text"),
                    "value_numeric": obs.get("value_numeric"),
                    "value_type": obs.get("value_type", "text"),
                    "unit": obs.get("unit"),
                    "reference_low": obs.get("reference_low"),
                    "reference_high": obs.get("reference_high"),
                    "reference_text": obs.get("reference_text"),
                    "status": status,
                    "interpretation": obs.get("interpretation"),
                    "notes": obs.get("notes"),
                    "source_page": obs.get("source_page"),
                    "source_text": obs.get("source_text"),
                    "confidence": obs.get("confidence", 0.9),
                    "needs_review": obs.get("needs_review", False),
                    "report_date": report_date,
                })

            # Step 6: Persist to database
            ObservationRepository.bulk_create(self.db, obs_records)

            # Step 7: Generate summary
            summary = self._generate_summary(extracted, len(obs_records))
            ReportRepository.update_metadata(self.db, report_id, summary=summary)

            # Step 8: Index in ChromaDB
            try:
                from app.rag.chroma import chroma_service
                chroma_service.index_report(
                    report_id=report_id,
                    patient_id=patient_id,
                    pages=pages,
                    report_metadata={
                        "report_type": metadata_update.get("report_type", ""),
                        "report_date": str(report_date) if report_date else "",
                        "laboratory": metadata_update.get("laboratory", ""),
                    },
                    observations=validated_obs,
                    api_key=self._api_key,
                )
            except Exception as e:
                logger.warning(f"ChromaDB indexing failed (non-fatal): {e}")

            # Step 9: Mark complete
            needs_review = any(obs.get("needs_review") for obs in validated_obs)
            final_status = ReportStatus.REQUIRES_REVIEW.value if needs_review else ReportStatus.COMPLETED.value
            review_msg = f"Extracted {len(obs_records)} observations. Some values may need review." if needs_review else f"Successfully extracted {len(obs_records)} observations."
            self._update_status(report_id, final_status, review_msg)

        except Exception as e:
            logger.exception(f"Report processing failed for {report_id}")
            self._update_status(report_id, ReportStatus.FAILED.value, f"Processing failed: {str(e)}")

    def _update_status(self, report_id: str, status: str, message: str):
        ReportRepository.update_status(self.db, report_id, status, message)

    def _parse_date(self, date_str: str):
        """Parse a date string in various formats."""
        if not date_str:
            return None
        from datetime import date
        import re

        # Try ISO format first
        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y"]:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _generate_summary(self, extracted: dict, obs_count: int) -> str:
        """Generate a brief summary of the report."""
        report_info = extracted.get("report", {})
        observations = extracted.get("observations", [])

        parts = []
        if report_info.get("report_type"):
            parts.append(f"Report type: {report_info['report_type'].replace('_', ' ').title()}")
        parts.append(f"{obs_count} test observations extracted")

        # Count statuses
        panels = set(obs.get("panel") for obs in observations if obs.get("panel"))
        if panels:
            parts.append(f"Panels: {', '.join(sorted(panels))}")

        return ". ".join(parts) + "."
