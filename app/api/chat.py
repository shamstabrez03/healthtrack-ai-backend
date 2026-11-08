"""Chat API routes — AI medical assistant (report-specific and history-wide)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.database.repositories import PatientRepository
from app.schemas.observations import ChatRequest, ChatResponse
from app.api.auth import get_current_user
from app.database.models import User

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/report", response_model=ChatResponse)
def chat_about_report(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat about a specific report."""
    patient = PatientRepository.get_by_id(db, data.patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not data.report_id:
        raise HTTPException(status_code=400, detail="report_id is required for report chat")

    try:
        from app.rag.chains import get_report_chat_response
        from app.api.auth import decrypt_api_key

        api_key = None
        if current_user.gemini_api_key_encrypted:
            api_key = decrypt_api_key(current_user.gemini_api_key_encrypted)

        if not api_key:
            raise HTTPException(status_code=400, detail="Please configure your Gemini API key in Settings")

        result = get_report_chat_response(
            db=db,
            api_key=api_key,
            model_name=current_user.gemini_model or "gemini-2.5-flash",
            question=data.message,
            patient_id=data.patient_id,
            report_id=data.report_id,
        )
        return ChatResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat error: {str(e)}")


@router.post("/history", response_model=ChatResponse)
def chat_about_history(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat across the patient's entire medical history."""
    patient = PatientRepository.get_by_id(db, data.patient_id, current_user.id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        from app.rag.chains import get_history_chat_response
        from app.api.auth import decrypt_api_key

        api_key = None
        if current_user.gemini_api_key_encrypted:
            api_key = decrypt_api_key(current_user.gemini_api_key_encrypted)

        if not api_key:
            raise HTTPException(status_code=400, detail="Please configure your Gemini API key in Settings")

        result = get_history_chat_response(
            db=db,
            api_key=api_key,
            model_name=current_user.gemini_model or "gemini-2.5-flash",
            question=data.message,
            patient_id=data.patient_id,
        )
        return ChatResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat error: {str(e)}")
