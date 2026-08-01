from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class WorkoutPlanCreate(BaseModel):
    title: str
    description: Optional[str] = None
    scheduled_date: date
    target_duration_minutes: int
    target_hr_zone: Optional[str] = None
    coach_id: Optional[int] = None
    ai_generated: bool = False


class WorkoutPlanOut(BaseModel):
    id: int
    athlete_id: int
    coach_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    scheduled_date: date
    target_duration_minutes: int
    target_hr_zone: Optional[str] = None
    status: str
    ai_generated: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkoutSessionCreate(BaseModel):
    workout_plan_id: Optional[int] = None
    activity_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    rpe_score: Optional[int] = None
    athlete_feedback: Optional[str] = None
    
    # Telemetry metrics passed during session log to evaluate Red Flags
    max_hr_recorded: Optional[int] = None
    avg_hr_recorded: Optional[int] = None
    symptoms_reported: Optional[str] = None


class WorkoutSessionOut(BaseModel):
    id: int
    athlete_id: int
    workout_plan_id: Optional[int] = None
    activity_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    rpe_score: Optional[int] = None
    athlete_feedback: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
