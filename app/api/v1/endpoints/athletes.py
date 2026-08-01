from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_db
from app.core.security import decrypt_sensitive_data, encrypt_sensitive_data
from app.models.user import AthleteProfile, CoachAthleteRelation, CoachProfile, User
from app.schemas.user import AthleteProfileOut, AthleteProfileUpdate, CoachProfileOut

router = APIRouter()


@router.get("/profile", response_model=AthleteProfileOut)
async def get_athlete_profile(
    athlete: AthleteProfile = Depends(get_current_athlete),
) -> Any:
    """
    Get current logged in athlete's profile.
    Decrypts medical notes protected under 152-FZ.
    """
    decrypted_med = decrypt_sensitive_data(athlete.medical_notes_encrypted)
    return AthleteProfileOut(
        id=athlete.id,
        user_id=athlete.user_id,
        date_of_birth=athlete.date_of_birth,
        height_cm=athlete.height_cm,
        weight_kg=athlete.weight_kg,
        max_hr=athlete.max_hr,
        rest_hr=athlete.rest_hr,
        medical_notes=decrypted_med if decrypted_med != "[ENCRYPTED_DATA_DECRYPTION_ERROR]" else None,
        created_at=athlete.created_at,
    )


@router.put("/profile", response_model=AthleteProfileOut)
async def update_athlete_profile(
    profile_in: AthleteProfileUpdate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Update athlete profile parameters and encrypt medical notes per 152-FZ.
    """
    if profile_in.date_of_birth is not None:
        athlete.date_of_birth = profile_in.date_of_birth
    if profile_in.height_cm is not None:
        athlete.height_cm = profile_in.height_cm
    if profile_in.weight_kg is not None:
        athlete.weight_kg = profile_in.weight_kg
    if profile_in.max_hr is not None:
        athlete.max_hr = profile_in.max_hr
    if profile_in.rest_hr is not None:
        athlete.rest_hr = profile_in.rest_hr
    if profile_in.medical_notes is not None:
        athlete.medical_notes_encrypted = encrypt_sensitive_data(profile_in.medical_notes)

    await db.commit()
    await db.refresh(athlete)

    decrypted_med = decrypt_sensitive_data(athlete.medical_notes_encrypted)
    return AthleteProfileOut(
        id=athlete.id,
        user_id=athlete.user_id,
        date_of_birth=athlete.date_of_birth,
        height_cm=athlete.height_cm,
        weight_kg=athlete.weight_kg,
        max_hr=athlete.max_hr,
        rest_hr=athlete.rest_hr,
        medical_notes=decrypted_med if decrypted_med != "[ENCRYPTED_DATA_DECRYPTION_ERROR]" else None,
        created_at=athlete.created_at,
    )


@router.get("/coaches", response_model=List[CoachProfileOut])
async def get_my_coaches(
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get list of coaches assigned to the athlete.
    """
    result = await db.execute(
        select(CoachProfile)
        .join(CoachAthleteRelation, CoachAthleteRelation.coach_id == CoachProfile.id)
        .where(
            CoachAthleteRelation.athlete_id == athlete.id,
            CoachAthleteRelation.status == "active"
        )
    )
    coaches = result.scalars().all()
    return coaches
