from datetime import datetime, timezone
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.models.user import AthleteProfile, CoachProfile, User
from app.models.workout import RedFlagLog, WorkoutPlan
from app.schemas.red_flag import RedFlagLogOut, RedFlagResolveRequest

router = APIRouter()


@router.get("/", response_model=List[RedFlagLogOut])
async def list_red_flags(
    only_unresolved: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    List red flag logs.
    Athletes see their own red flags; Coaches/Admins see red flags for their managed users.
    """
    query = select(RedFlagLog)

    if current_user.role == "athlete":
        ath_res = await db.execute(
            select(AthleteProfile).where(AthleteProfile.user_id == current_user.id)
        )
        ath = ath_res.scalar_one_or_none()
        if not ath:
            return []
        query = query.where(RedFlagLog.athlete_id == ath.id)
    
    if only_unresolved:
        query = query.where(RedFlagLog.resolved.is_(False))

    query = query.order_by(RedFlagLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{red_flag_id}/resolve", response_model=RedFlagLogOut)
async def resolve_red_flag(
    red_flag_id: int,
    resolve_in: RedFlagResolveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Clear/Resolve a red flag lock (Coach/Doctor approval).
    Unlocks blocked athlete workout plans.
    """
    result = await db.execute(
        select(RedFlagLog).where(RedFlagLog.id == red_flag_id)
    )
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Red flag log not found"
        )

    flag.resolved = True
    flag.resolved_by_id = current_user.id
    flag.resolved_at = datetime.now(timezone.utc)
    if resolve_in.resolution_notes:
        flag.action_taken = f"{flag.action_taken} | Resolution Notes: {resolve_in.resolution_notes}"

    # Unlock athlete's workout plans if no remaining unresolved L1/L2 flags exist
    athlete_id = flag.athlete_id
    remaining_res = await db.execute(
        select(RedFlagLog).where(
            RedFlagLog.athlete_id == athlete_id,
            RedFlagLog.resolved.is_(False),
            RedFlagLog.id != red_flag_id,
            RedFlagLog.level.in_(["LEVEL_1_EMERGENCY", "LEVEL_2_MEDICAL"])
        )
    )
    if not remaining_res.scalars().all():
        await db.execute(
            update(WorkoutPlan)
            .where(
                WorkoutPlan.athlete_id == athlete_id,
                WorkoutPlan.status.like("locked_%")
            )
            .values(status="planned")
        )

    await db.commit()
    await db.refresh(flag)
    return flag
