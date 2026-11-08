"""Data access layer for database operations."""

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, extract
from typing import Optional, List
from datetime import datetime, date
from app.database.models import User, Patient, Report, Observation, ReportStatus, ObservationStatus


class UserRepository:
    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_by_id(db: Session, user_id: str) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create(db: Session, email: str, hashed_password: str, name: str) -> User:
        user = User(email=email, hashed_password=hashed_password, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_gemini_key(db: Session, user_id: str, encrypted_key: Optional[str], model: Optional[str] = None) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.gemini_api_key_encrypted = encrypted_key
            if model:
                user.gemini_model = model
            db.commit()
            db.refresh(user)
        return user


class PatientRepository:
    @staticmethod
    def get_all_for_user(db: Session, user_id: str) -> List[Patient]:
        patients = db.query(Patient).filter(Patient.user_id == user_id).all()
        return patients

    @staticmethod
    def get_by_id(db: Session, patient_id: str, user_id: str) -> Optional[Patient]:
        return db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.user_id == user_id
        ).first()

    @staticmethod
    def create(db: Session, user_id: str, name: str, relationship_type: str = "self",
               date_of_birth=None, gender=None) -> Patient:
        patient = Patient(
            user_id=user_id,
            name=name,
            relationship_type=relationship_type,
            date_of_birth=date_of_birth,
            gender=gender,
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        return patient

    @staticmethod
    def update(db: Session, patient_id: str, user_id: str, **kwargs) -> Optional[Patient]:
        patient = db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.user_id == user_id
        ).first()
        if patient:
            for key, value in kwargs.items():
                if value is not None and hasattr(patient, key):
                    setattr(patient, key, value)
            db.commit()
            db.refresh(patient)
        return patient

    @staticmethod
    def delete(db: Session, patient_id: str, user_id: str) -> bool:
        patient = db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.user_id == user_id
        ).first()
        if patient:
            db.delete(patient)
            db.commit()
            return True
        return False

    @staticmethod
    def get_report_count(db: Session, patient_id: str) -> int:
        return db.query(func.count(Report.id)).filter(Report.patient_id == patient_id).scalar() or 0

    @staticmethod
    def get_last_report_date(db: Session, patient_id: str) -> Optional[date]:
        result = db.query(func.max(Report.report_date)).filter(Report.patient_id == patient_id).scalar()
        return result


class ReportRepository:
    @staticmethod
    def create(db: Session, patient_id: str, file_path: str, original_filename: str,
               file_hash: Optional[str] = None) -> Report:
        report = Report(
            patient_id=patient_id,
            file_path=file_path,
            original_filename=original_filename,
            file_hash=file_hash,
            status=ReportStatus.UPLOADED.value,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    @staticmethod
    def get_by_id(db: Session, report_id: str, patient_id: str) -> Optional[Report]:
        return db.query(Report).filter(
            Report.id == report_id,
            Report.patient_id == patient_id
        ).first()

    @staticmethod
    def get_all_for_patient(db: Session, patient_id: str, report_type: Optional[str] = None,
                            skip: int = 0, limit: int = 50) -> List[Report]:
        query = db.query(Report).filter(Report.patient_id == patient_id)
        if report_type:
            query = query.filter(Report.report_type == report_type)
        return query.order_by(desc(Report.report_date), desc(Report.upload_timestamp)).offset(skip).limit(limit).all()

    @staticmethod
    def get_count_for_patient(db: Session, patient_id: str) -> int:
        return db.query(func.count(Report.id)).filter(Report.patient_id == patient_id).scalar() or 0

    @staticmethod
    def get_reports_this_year(db: Session, patient_id: str) -> int:
        current_year = datetime.utcnow().year
        return db.query(func.count(Report.id)).filter(
            Report.patient_id == patient_id,
            extract('year', Report.upload_timestamp) == current_year
        ).scalar() or 0

    @staticmethod
    def update_status(db: Session, report_id: str, status: str, message: Optional[str] = None):
        report = db.query(Report).filter(Report.id == report_id).first()
        if report:
            report.status = status
            if message:
                report.processing_message = message
            if status == ReportStatus.COMPLETED.value:
                report.processed_at = datetime.utcnow()
            db.commit()
            db.refresh(report)
        return report

    @staticmethod
    def update_metadata(db: Session, report_id: str, **kwargs):
        report = db.query(Report).filter(Report.id == report_id).first()
        if report:
            for key, value in kwargs.items():
                if hasattr(report, key):
                    setattr(report, key, value)
            db.commit()
            db.refresh(report)
        return report

    @staticmethod
    def find_duplicate(db: Session, patient_id: str, file_hash: str) -> Optional[Report]:
        return db.query(Report).filter(
            Report.patient_id == patient_id,
            Report.file_hash == file_hash,
        ).first()

    @staticmethod
    def delete(db: Session, report_id: str, patient_id: str) -> Optional[Report]:
        """Delete report and return it (for cleanup). Cascades to observations."""
        report = db.query(Report).filter(
            Report.id == report_id,
            Report.patient_id == patient_id
        ).first()
        if report:
            db.delete(report)
            db.commit()
            return report
        return None

    @staticmethod
    def get_latest_reports(db: Session, patient_id: str, limit: int = 5) -> List[Report]:
        return db.query(Report).filter(
            Report.patient_id == patient_id,
            Report.status == ReportStatus.COMPLETED.value
        ).order_by(desc(Report.report_date), desc(Report.upload_timestamp)).limit(limit).all()


class ObservationRepository:
    @staticmethod
    def bulk_create(db: Session, observations: List[dict]) -> List[Observation]:
        obs_objects = []
        for obs_data in observations:
            obs = Observation(**obs_data)
            db.add(obs)
            obs_objects.append(obs)
        db.commit()
        for obs in obs_objects:
            db.refresh(obs)
        return obs_objects

    @staticmethod
    def get_for_report(db: Session, report_id: str, patient_id: str) -> List[Observation]:
        return db.query(Observation).filter(
            Observation.report_id == report_id,
            Observation.patient_id == patient_id
        ).order_by(Observation.panel, Observation.test_name).all()

    @staticmethod
    def get_attention_items(db: Session, patient_id: str, limit: int = 50) -> List[Observation]:
        """Get observations that need attention from the patient's latest report only."""
        latest_report = db.query(Report).filter(
            Report.patient_id == patient_id,
            Report.status.in_([ReportStatus.COMPLETED.value, ReportStatus.REQUIRES_REVIEW.value])
        ).order_by(desc(Report.report_date), desc(Report.upload_timestamp)).first()

        if not latest_report:
            return []

        return db.query(Observation).filter(
            Observation.report_id == latest_report.id,
            Observation.patient_id == patient_id,
            Observation.status.in_([
                ObservationStatus.ATTENTION.value,
                ObservationStatus.SIGNIFICANT.value,
                ObservationStatus.POTENTIALLY_URGENT.value,
            ])
        ).order_by(Observation.panel, Observation.test_name).limit(limit).all()

    @staticmethod
    def get_attention_count(db: Session, patient_id: str) -> int:
        """Count observations needing attention in the current/latest report only."""
        latest_report = db.query(Report).filter(
            Report.patient_id == patient_id,
            Report.status.in_([ReportStatus.COMPLETED.value, ReportStatus.REQUIRES_REVIEW.value])
        ).order_by(desc(Report.report_date), desc(Report.upload_timestamp)).first()

        if not latest_report:
            return 0

        count = db.query(func.count(Observation.id)).filter(
            Observation.report_id == latest_report.id,
            Observation.patient_id == patient_id,
            Observation.status.in_([
                ObservationStatus.ATTENTION.value,
                ObservationStatus.SIGNIFICANT.value,
                ObservationStatus.POTENTIALLY_URGENT.value,
            ])
        ).scalar()
        return count or 0

    @staticmethod
    def get_tracked_test_count(db: Session, patient_id: str) -> int:
        return db.query(func.count(func.distinct(Observation.canonical_test_name))).filter(
            Observation.patient_id == patient_id,
            Observation.canonical_test_name.isnot(None),
        ).scalar() or 0

    @staticmethod
    def get_trend_data(db: Session, patient_id: str, canonical_test_name: str,
                       start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Observation]:
        query = db.query(Observation).filter(
            Observation.patient_id == patient_id,
            Observation.canonical_test_name == canonical_test_name,
            Observation.value_numeric.isnot(None),
        )
        if start_date:
            query = query.filter(Observation.report_date >= start_date)
        if end_date:
            query = query.filter(Observation.report_date <= end_date)
        return query.order_by(Observation.report_date).all()

    @staticmethod
    def get_available_tests(db: Session, patient_id: str) -> List[dict]:
        """Get list of canonical test names with latest values for a patient."""
        results = db.query(
            Observation.canonical_test_name,
            Observation.test_name,
            Observation.unit,
            func.count(Observation.id).label("count"),
        ).filter(
            Observation.patient_id == patient_id,
            Observation.canonical_test_name.isnot(None),
            Observation.value_numeric.isnot(None),
        ).group_by(
            Observation.canonical_test_name,
            Observation.test_name,
            Observation.unit,
        ).all()

        tests = []
        for r in results:
            tests.append({
                "canonical_name": r.canonical_test_name,
                "display_name": r.test_name,
                "unit": r.unit,
                "data_point_count": r.count,
            })
        return tests

    @staticmethod
    def get_observation_count_for_report(db: Session, report_id: str) -> int:
        return db.query(func.count(Observation.id)).filter(
            Observation.report_id == report_id
        ).scalar() or 0

    @staticmethod
    def get_abnormal_count_for_report(db: Session, report_id: str) -> int:
        return db.query(func.count(Observation.id)).filter(
            Observation.report_id == report_id,
            Observation.status.in_([
                ObservationStatus.ATTENTION.value,
                ObservationStatus.SIGNIFICANT.value,
                ObservationStatus.POTENTIALLY_URGENT.value,
            ])
        ).scalar() or 0
