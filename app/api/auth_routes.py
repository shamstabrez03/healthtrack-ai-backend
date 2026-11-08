"""Auth API routes — register, login, current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.database.repositories import UserRepository, PatientRepository
from app.schemas.auth import UserCreate, UserLogin, Token, UserResponse
from app.api.auth import hash_password, verify_password, create_access_token, get_current_user
from app.database.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user and create their default 'self' patient profile."""
    existing = UserRepository.get_by_email(db, user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = UserRepository.create(
        db,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        name=user_data.name,
    )

    # Create default "self" patient profile
    PatientRepository.create(db, user_id=user.id, name=user.name, relationship_type="self")

    token = create_access_token(data={"sub": user.id})
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login with email and password."""
    user = UserRepository.get_by_email(db, user_data.email)
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={"sub": user.id})
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at,
        has_gemini_key=current_user.gemini_api_key_encrypted is not None,
        gemini_model=current_user.gemini_model,
    )
