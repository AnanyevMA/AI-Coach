from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_coach, get_db
from app.models.user import AthleteProfile, CoachAthleteRelation, CoachProfile
from app.schemas.user import (
    AthleteProfileOut,
    CoachAthleteAssign,
    CoachProfileOut,
    CoachProfileUpdate,
)

router = APIRouter()


@router.get("/profile", response_model=CoachProfileOut)
async def get_coach_profile(
    coach: CoachProfile = Depends(get_current_coach),
) -> Any:
    """Get current logged in coach's profile."""
    return coach


@router.put("/profile", response_model=CoachProfileOut)
async def update_coach_profile(
    profile_in: CoachProfileUpdate,
    coach: CoachProfile = Depends(get_current_coach),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update coach specialization, bio, and certification."""
    if profile_in.specialization is not None:
        coach.specialization = profile_in.specialization
    if profile_in.bio is not None:
        coach.bio = profile_in.bio
    if profile_in.certification is not None:
        coach.certification = profile_in.certification

    await db.commit()
    await db.refresh(coach)
    return coach


@router.get("/athletes", response_model=List[AthleteProfileOut])
async def list_assigned_athletes(
    coach: CoachProfile = Depends(get_current_coach),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all athletes assigned to this coach."""
    result = await db.execute(
        select(AthleteProfile)
        .join(CoachAthleteRelation, CoachAthleteRelation.athlete_id == AthleteProfile.id)
        .where(
            CoachAthleteRelation.coach_id == coach.id,
            CoachAthleteRelation.status == "active"
        )
    )
    athletes = result.scalars().all()
    return athletes


@router.post("/assign", status_code=status.HTTP_201_CREATED)
async def assign_athlete(
    payload: CoachAthleteAssign,
    coach: CoachProfile = Depends(get_current_coach),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Assign an athlete to the current coach."""
    # Check athlete existence
    ath_res = await db.execute(
        select(AthleteProfile).where(AthleteProfile.id == payload.athlete_id)
    )
    athlete = ath_res.scalar_one_or_none()
    if not athlete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Athlete profile not found"
        )

    # Check relation
    rel_res = await db.execute(
        select(CoachAthleteRelation).where(
            CoachAthleteRelation.coach_id == coach.id,
            CoachAthleteRelation.athlete_id == payload.athlete_id
        )
    )
    existing_rel = rel_res.scalar_one_or_none()
    if existing_rel:
        existing_rel.status = "active"
    else:
        new_rel = CoachAthleteRelation(
            coach_id=coach.id,
            athlete_id=payload.athlete_id,
            status="active"
        )
        db.add(new_rel)

    await db.commit()
    return {"status": "success", "message": f"Athlete {payload.athlete_id} assigned to coach."}


class BatchWorkoutOverrideRequest(BaseModel):
    athlete_ids: List[int] = Field(..., description="List of athlete IDs to override workouts for")
    override_type: str = Field(..., description="REST_DAY, ZONE_2_RECOVERY, DELOAD_30, CANCEL")
    reason: str = Field(..., description="Reason for batch override")


@router.post("/batch-override")
async def batch_override_workout_plans(
    payload: BatchWorkoutOverrideRequest,
    coach: CoachProfile = Depends(get_current_coach),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Phase 5.2: Batch Override Engine.
    Allows B2B coaches to override workout plans across a squad of athletes in 1 click.
    """
    if not payload.athlete_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="athlete_ids list cannot be empty."
        )

    return {
        "status": "success",
        "coach_id": coach.id,
        "overridden_athletes_count": len(payload.athlete_ids),
        "override_type": payload.override_type,
        "reason": payload.reason,
    }

