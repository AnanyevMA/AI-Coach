from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class TelemetryRecordCreate(BaseModel):
    timestamp: datetime
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    power: Optional[float] = None
    speed: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    raw_payload: Optional[str] = None


class TelemetryRecordOut(BaseModel):
    id: int
    athlete_id: int
    timestamp: datetime
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    power: Optional[float] = None
    speed: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ActivityCreate(BaseModel):
    title: str
    activity_type: str
    start_time: datetime
    duration_seconds: int
    distance_meters: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    total_elevation_gain: Optional[float] = None
    fit_file_path: Optional[str] = None


class ActivityOut(BaseModel):
    id: int
    athlete_id: int
    title: str
    activity_type: str
    start_time: datetime
    duration_seconds: int
    distance_meters: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    total_elevation_gain: Optional[float] = None
    fit_file_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HRVDataCreate(BaseModel):
    measured_at: datetime
    rmssd: float
    sdnn: Optional[float] = None
    pnn50: Optional[float] = None
    readiness_score: Optional[float] = None
    raw_metrics: Optional[str] = None


class HRVDataOut(BaseModel):
    id: int
    athlete_id: int
    measured_at: datetime
    rmssd: float
    sdnn: Optional[float] = None
    pnn50: Optional[float] = None
    readiness_score: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
