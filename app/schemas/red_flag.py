from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RedFlagLogOut(BaseModel):
    id: int
    athlete_id: int
    workout_session_id: Optional[int] = None
    level: str
    trigger_condition: str
    action_taken: str
    resolved: bool
    resolved_by_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RedFlagResolveRequest(BaseModel):
    resolution_notes: Optional[str] = None
