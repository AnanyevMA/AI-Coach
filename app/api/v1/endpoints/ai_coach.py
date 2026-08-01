from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_db
from app.core.config import settings
from app.core.rate_limiter import RateLimiter
from app.medical.red_flags import RedFlagsTriageEngine, TriageAssessmentInput, TriageLevel
from app.models.telemetry import Activity, HRVData
from app.models.user import AthleteProfile
from app.models.workout import WorkoutPlan, WorkoutSession, RedFlagLog
from app.services.ai_coach_engine import (
    AICoachPlanResponse,
    ActivityAnalysisResponse,
    RedFlagBlockError,
    ai_coach_engine,
)
from app.services.fallback_engine import FallbackInput, offline_fallback_engine
from app.services.red_flag_service import red_flag_service

router = APIRouter()


class AICoachGeneratePlanRequest(BaseModel):
    scheduled_date: Optional[date] = None
    original_activity_type: str = "RUNNING"
    target_duration_minutes: int = 60
    target_hr_zone: str = "Z3_TEMPO"
    goal: str = "Endurance & Performance"

    # Red Flag Indicators
    chest_pain_or_pressure: bool = False
    syncope_or_dizziness: bool = False
    palpitations_at_rest: bool = False
    dark_urine_rhabdo_suspect: bool = False
    fever_celsius: float = 36.6
    inability_to_bear_weight: bool = False
    knee_pain_vas: int = Field(default=0, ge=0, le=10)

    # Subjective Hooper Questionnaire (1 to 7 scale)
    sleep_quality: int = Field(default=4, ge=1, le=7)
    stress_level: int = Field(default=4, ge=1, le=7)
    fatigue_level: int = Field(default=4, ge=1, le=7)
    doms_score: int = Field(default=0, ge=0, le=10)

    # Telemetry Overrides
    hrv_z_score: Optional[float] = None
    acwr: Optional[float] = None
    rhr_elevation_bpm: Optional[int] = None
    force_offline_fallback: bool = False


class AICoachAnalyzeActivityRequest(BaseModel):
    activity_id: Optional[int] = None
    workout_plan_id: Optional[int] = None
    rpe_score: Optional[int] = Field(default=None, ge=1, le=10)
    athlete_feedback: Optional[str] = None
    duration_seconds: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_power: Optional[float] = None
    avg_cadence: Optional[int] = None


@router.post(
    "/generate-plan",
    response_model=AICoachPlanResponse,
    dependencies=[Depends(RateLimiter(times=settings.AI_COACH_RATE_LIMIT_PLAN, seconds=60, prefix="ai_coach_plan"))],
)
async def generate_adapted_workout_plan(
    req: AICoachGeneratePlanRequest,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Generate an AI-adapted workout plan for the athlete.
    Enforces RedFlagsTriageEngine pre-checks: Level 1 Emergency or Level 2 Medical Lock BLOCKS LLM calls.
    Supports Gemini 1.5 Flash by default with Gemini 1.5 Pro fallback or offline fallback engine.
    """
    # 1. Fetch latest HRV data if not provided
    hrv_z = req.hrv_z_score
    if hrv_z is None:
        hrv_res = await db.execute(
            select(HRVData)
            .where(HRVData.athlete_id == athlete.id)
            .order_by(HRVData.measured_at.desc())
            .limit(1)
        )
        latest_hrv = hrv_res.scalar_one_or_none()
        if latest_hrv:
            hrv_z = round((latest_hrv.rmssd - 50.0) / 10.0, 2)
        else:
            hrv_z = 0.0

    acwr = req.acwr if req.acwr is not None else 1.0
    rhr_elev = req.rhr_elevation_bpm if req.rhr_elevation_bpm is not None else 0

    # 2. Build Red Flag Triage Input
    triage_input = TriageAssessmentInput(
        chest_pain_or_pressure=req.chest_pain_or_pressure,
        syncope_or_dizziness=req.syncope_or_dizziness,
        palpitations_at_rest=req.palpitations_at_rest,
        dark_urine_rhabdo_suspect=req.dark_urine_rhabdo_suspect,
        fever_celsius=req.fever_celsius,
        inability_to_bear_weight=req.inability_to_bear_weight,
        knee_pain_vas=req.knee_pain_vas,
        hrv_z_score=hrv_z,
        acwr=acwr,
        rhr_elevation_bpm=rhr_elev,
    )

    # 3. Check Red Flags BEFORE Calling AI Engine
    triage_res = ai_coach_engine.triage_engine.evaluate(triage_input)
    if triage_res.triage_level in [TriageLevel.LEVEL_1_EMERGENCY, TriageLevel.LEVEL_2_MEDICAL_REFERRAL]:
        # Log red flag
        log_entry = RedFlagLog(
            athlete_id=athlete.id,
            level=triage_res.triage_level.value,
            trigger_condition=triage_res.message,
            action_taken=triage_res.action.value,
            resolved=False,
        )
        db.add(log_entry)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "RED_FLAG_BLOCKED",
                "triage_level": triage_res.triage_level.value,
                "action": triage_res.action.value,
                "message": triage_res.message,
                "call_emergency": triage_res.call_emergency,
                "referral_specialist": triage_res.referral_specialist,
            },
        )

    # 4. Assemble Context
    act_res = await db.execute(
        select(Activity)
        .where(Activity.athlete_id == athlete.id)
        .order_by(Activity.start_time.desc())
        .limit(5)
    )
    recent_acts = act_res.scalars().all()
    recent_summary = [
        {
            "date": a.start_time.strftime("%Y-%m-%d"),
            "title": a.title,
            "duration_min": a.duration_seconds // 60,
            "avg_hr": a.avg_hr,
        }
        for a in recent_acts
    ]

    hooper_dict = {
        "sleep": req.sleep_quality,
        "stress": req.stress_level,
        "fatigue": req.fatigue_level,
        "doms": req.doms_score,
    }

    context = ai_coach_engine.assemble_context(
        athlete_id=athlete.id,
        athlete_name=f"Athlete #{athlete.id}",
        max_hr=athlete.max_hr or 190,
        rest_hr=athlete.rest_hr or 60,
        hrv_z_score=hrv_z,
        acwr=acwr,
        doms_score=req.doms_score,
        recent_workouts=recent_summary,
        goal=req.goal,
        knee_pain_vas=req.knee_pain_vas,
        rhr_elevation_bpm=rhr_elev,
        medical_notes=athlete.medical_notes_encrypted,
        hooper_survey=hooper_dict,
        date_of_birth=str(athlete.date_of_birth) if athlete.date_of_birth else None,
        height_cm=athlete.height_cm,
        weight_kg=athlete.weight_kg,
    )

    # 5. Generate Plan via Gemini AI Engine or Offline Fallback Engine
    if req.force_offline_fallback:
        fb_input = FallbackInput(
            scheduled_activity_type=req.original_activity_type,
            original_duration_minutes=req.target_duration_minutes,
            original_target_zone=req.target_hr_zone,
            hrv_z_score=hrv_z,
            acwr=acwr,
            doms_score=req.doms_score,
            knee_pain_vas=req.knee_pain_vas,
            rhr_elevation_bpm=rhr_elev,
            fatigue_score=req.fatigue_level,
        )
        fb_plan = offline_fallback_engine.adapt_workout(fb_input)
        plan = AICoachPlanResponse(
            plan_title=f"Offline Adapted {fb_plan.adapted_activity_type.value}",
            summary=fb_plan.coaching_notes,
            workout_type=fb_plan.adapted_activity_type.value,
            total_duration_minutes=fb_plan.adapted_duration_minutes,
            target_hr_zone=fb_plan.adapted_target_zone,
            safety_assessment={
                "is_safe": True,
                "risk_level": "CAUTION" if fb_plan.intensity_capped else "LOW",
                "warnings": fb_plan.adaptation_reasons,
            },
            intervals=[
                {
                    "name": "Adapted Session",
                    "duration_minutes": fb_plan.adapted_duration_minutes,
                    "target_hr_zone": fb_plan.adapted_target_zone,
                    "description": fb_plan.coaching_notes,
                }
            ],
            coach_advice=fb_plan.coaching_notes,
        )
    else:
        try:
            plan = ai_coach_engine.generate_plan(
                triage_input=triage_input, context=context
            )
        except RedFlagBlockError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )

    # 6. Save Plan in Database
    plan_date = req.scheduled_date or date.today()
    db_plan = WorkoutPlan(
        athlete_id=athlete.id,
        title=plan.plan_title,
        description=plan.summary,
        scheduled_date=plan_date,
        target_duration_minutes=plan.total_duration_minutes,
        target_hr_zone=plan.target_hr_zone,
        status="planned",
        ai_generated=True,
    )
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)

    return plan


@router.post(
    "/analyze-activity",
    response_model=ActivityAnalysisResponse,
    dependencies=[Depends(RateLimiter(times=settings.AI_COACH_RATE_LIMIT_ANALYZE, seconds=60, prefix="ai_coach_analyze"))],
)
async def analyze_completed_activity(
    req: AICoachAnalyzeActivityRequest,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Analyze completed workout activity using AI Coach Engine against target workout plan and readiness context.
    """
    activity_data: Dict[str, Any] = {}
    plan_data: Dict[str, Any] = {}

    if req.activity_id:
        act_res = await db.execute(
            select(Activity).where(
                Activity.id == req.activity_id, Activity.athlete_id == athlete.id
            )
        )
        act = act_res.scalar_one_or_none()
        if act:
            activity_data = {
                "title": act.title,
                "activity_type": act.activity_type,
                "duration_seconds": act.duration_seconds,
                "avg_hr": act.avg_hr,
                "max_hr": act.max_hr,
                "distance_meters": act.distance_meters,
            }

    if not activity_data:
        activity_data = {
            "title": "Logged Activity",
            "duration_seconds": req.duration_seconds or 3600,
            "avg_hr": req.avg_hr or 145,
            "max_hr": req.max_hr or 170,
            "avg_power": req.avg_power,
            "avg_cadence": req.avg_cadence,
            "rpe_score": req.rpe_score or 6,
        }

    if req.workout_plan_id:
        plan_res = await db.execute(
            select(WorkoutPlan).where(
                WorkoutPlan.id == req.workout_plan_id, WorkoutPlan.athlete_id == athlete.id
            )
        )
        plan = plan_res.scalar_one_or_none()
        if plan:
            plan_data = {
                "title": plan.title,
                "total_duration_minutes": plan.target_duration_minutes,
                "target_hr_zone": plan.target_hr_zone,
            }

    athlete_context = {
        "max_hr": athlete.max_hr or 190,
        "rest_hr": athlete.rest_hr or 60,
    }

    # Analyze activity
    analysis = ai_coach_engine.analyze_activity(
        activity_data=activity_data, plan_data=plan_data, athlete_context=athlete_context
    )

    # Save session log if workout_plan_id or activity_id provided
    if req.workout_plan_id or req.activity_id:
        session = WorkoutSession(
            athlete_id=athlete.id,
            workout_plan_id=req.workout_plan_id,
            activity_id=req.activity_id,
            start_time=datetime.now(timezone.utc),
            rpe_score=req.rpe_score,
            athlete_feedback=req.athlete_feedback,
        )
        db.add(session)
        await db.commit()

        if req.max_hr:
            await red_flag_service.evaluate_athlete_status(
                db=db,
                athlete_id=athlete.id,
                workout_session_id=session.id,
                current_hr=req.max_hr,
                rpe_score=req.rpe_score,
                symptoms_text=req.athlete_feedback,
            )

    return analysis
