from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    decrypt_sensitive_data,
    encrypt_sensitive_data,
    get_password_hash,
    verify_password,
)
from app.models.audit import ConsentLog
from app.models.user import AthleteProfile, CoachProfile, User
from app.schemas.auth import Token, UserLogin, UserRegister
from app.schemas.user import UserOut

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Register a new athlete or coach account.
    Encrypts sensitive PII (Full Name, Phone) using AES-256-GCM and logs 152-FZ consents.
    """
    # 1. Check if user already exists
    existing = await db.execute(select(User).where(User.email == user_in.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists."
        )

    # 2. Encrypt PII per Federal Law 152-FZ
    full_name_enc = encrypt_sensitive_data(user_in.full_name) if user_in.full_name else None
    phone_enc = encrypt_sensitive_data(user_in.phone) if user_in.phone else None

    # 3. Create User record
    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name_encrypted=full_name_enc,
        phone_encrypted=phone_enc,
        role=user_in.role,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()  # Get user.id

    # 4. Create Profile according to role
    if user_in.role == "coach":
        coach_prof = CoachProfile(user_id=new_user.id)
        db.add(coach_prof)
    else:
        athlete_prof = AthleteProfile(user_id=new_user.id)
        db.add(athlete_prof)

    # 5. Log Mandatory 152-FZ Consent Records
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    if user_in.consent_personal_data:
        db.add(
            ConsentLog(
                user_id=new_user.id,
                consent_type="personal_data_processing",
                is_granted=True,
                ip_address=client_ip,
                user_agent=user_agent,
                legal_document_version=user_in.legal_document_version,
            )
        )
    if user_in.consent_health_data:
        db.add(
            ConsentLog(
                user_id=new_user.id,
                consent_type="health_data_processing",
                is_granted=True,
                ip_address=client_ip,
                user_agent=user_agent,
                legal_document_version=user_in.legal_document_version,
            )
        )

    await db.commit()
    await db.refresh(new_user)

    return UserOut(
        id=new_user.id,
        email=new_user.email,
        role=new_user.role,
        is_active=new_user.is_active,
        full_name=user_in.full_name,
        phone=user_in.phone,
        created_at=new_user.created_at,
    )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    access_token = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role, "email": user.email}
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserOut)
async def read_users_me(
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get current logged in user details, decrypting PII for authorized owner.
    """
    decrypted_name = decrypt_sensitive_data(current_user.full_name_encrypted)
    decrypted_phone = decrypt_sensitive_data(current_user.phone_encrypted)

    return UserOut(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        full_name=decrypted_name if decrypted_name != "[ENCRYPTED_DATA_DECRYPTION_ERROR]" else None,
        phone=decrypted_phone if decrypted_phone != "[ENCRYPTED_DATA_DECRYPTION_ERROR]" else None,
        created_at=current_user.created_at,
    )
