from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_current_user, get_db
from app.models.user import AthleteProfile, User
from app.models.workout import WorkoutPlan, WorkoutSession
from app.schemas.workout import (
    WorkoutPlanCreate,
    WorkoutPlanOut,
    WorkoutSessionCreate,
    WorkoutSessionOut,
)
from app.services.red_flag_service import red_flag_service

router = APIRouter()


@router.get("/plans", response_model=List[WorkoutPlanOut])
async def list_workout_plans(
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve scheduled workout plans for current athlete."""
    result = await db.execute(
        select(WorkoutPlan)
        .where(WorkoutPlan.athlete_id == athlete.id)
        .order_by(WorkoutPlan.scheduled_date.asc())
    )
    return result.scalars().all()


@router.post("/plans", response_model=WorkoutPlanOut, status_code=status.HTTP_201_CREATED)
async def create_workout_plan(
    plan_in: WorkoutPlanCreate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new training workout plan."""
    plan = WorkoutPlan(
        athlete_id=athlete.id,
        coach_id=plan_in.coach_id,
        title=plan_in.title,
        description=plan_in.description,
        scheduled_date=plan_in.scheduled_date,
        target_duration_minutes=plan_in.target_duration_minutes,
        target_hr_zone=plan_in.target_hr_zone,
        status="planned",
        ai_generated=plan_in.ai_generated,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.post("/sessions", response_model=WorkoutSessionOut, status_code=status.HTTP_201_CREATED)
async def log_workout_session(
    session_in: WorkoutSessionCreate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Log a completed workout session with RPE and athlete feedback.
    Executes automated Red Flag Triage engine immediately after recording.
    """
    sess = WorkoutSession(
        workout_plan_id=session_in.workout_plan_id,
        athlete_id=athlete.id,
        activity_id=session_in.activity_id,
        start_time=session_in.start_time,
        end_time=session_in.end_time,
        rpe_score=session_in.rpe_score,
        athlete_feedback=session_in.athlete_feedback,
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)

    # Update associated workout plan status if linked
    if session_in.workout_plan_id:
        plan_res = await db.execute(
            select(WorkoutPlan).where(WorkoutPlan.id == session_in.workout_plan_id)
        )
        plan = plan_res.scalar_one_or_none()
        if plan:
            plan.status = "completed"
            await db.commit()

    # Trigger Red Flag Service Triage
    await red_flag_service.evaluate_athlete_status(
        db=db,
        athlete_id=athlete.id,
        workout_session_id=sess.id,
        current_hr=session_in.max_hr_recorded,
        rpe_score=session_in.rpe_score,
        symptoms_text=session_in.symptoms_reported or session_in.athlete_feedback,
    )

    return sess
