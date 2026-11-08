"""Settings API routes — Gemini API key management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from app.database.session import get_db
from app.database.repositories import UserRepository
from app.api.auth import get_current_user, encrypt_api_key, decrypt_api_key
from app.database.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class GeminiKeyRequest(BaseModel):
    api_key: str
    model: Optional[str] = None


class GeminiKeyResponse(BaseModel):
    has_key: bool
    model: Optional[str] = None


class TestGeminiResponse(BaseModel):
    success: bool
    message: str
    model: Optional[str] = None


@router.get("/gemini", response_model=GeminiKeyResponse)
def get_gemini_settings(current_user: User = Depends(get_current_user)):
    """Check if a Gemini API key is configured (never returns the key itself)."""
    return GeminiKeyResponse(
        has_key=current_user.gemini_api_key_encrypted is not None,
        model=current_user.gemini_model,
    )


@router.post("/gemini-key", response_model=GeminiKeyResponse)
def save_gemini_key(
    data: GeminiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a Gemini API key (encrypted). Never returns the key."""
    encrypted = encrypt_api_key(data.api_key)
    model = data.model or current_user.gemini_model or "gemini-2.5-flash"
    UserRepository.update_gemini_key(db, current_user.id, encrypted, model)
    return GeminiKeyResponse(has_key=True, model=model)


@router.delete("/gemini-key")
def remove_gemini_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the stored Gemini API key."""
    UserRepository.update_gemini_key(db, current_user.id, None)
    return {"message": "API key removed"}


@router.post("/test-gemini", response_model=TestGeminiResponse)
def test_gemini_connection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test the Gemini API connection with the stored key."""
    if not current_user.gemini_api_key_encrypted:
        raise HTTPException(status_code=400, detail="No Gemini API key configured")

    try:
        api_key = decrypt_api_key(current_user.gemini_api_key_encrypted)
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(current_user.gemini_model or "gemini-2.5-flash")
        response = model.generate_content("Say 'Connection successful' in exactly two words.")
        return TestGeminiResponse(
            success=True,
            message="Connection successful",
            model=current_user.gemini_model,
        )
    except Exception as e:
        return TestGeminiResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
        )
