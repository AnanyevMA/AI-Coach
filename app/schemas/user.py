from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    full_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AthleteProfileCreate(BaseModel):
    date_of_birth: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    rest_hr: Optional[int] = None
    medical_notes: Optional[str] = None


class AthleteProfileUpdate(BaseModel):
    date_of_birth: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    rest_hr: Optional[int] = None
    medical_notes: Optional[str] = None


class AthleteProfileOut(BaseModel):
    id: int
    user_id: int
    date_of_birth: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    rest_hr: Optional[int] = None
    medical_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoachProfileCreate(BaseModel):
    specialization: Optional[str] = None
    bio: Optional[str] = None
    certification: Optional[str] = None


class CoachProfileUpdate(BaseModel):
    specialization: Optional[str] = None
    bio: Optional[str] = None
    certification: Optional[str] = None


class CoachProfileOut(BaseModel):
    id: int
    user_id: int
    specialization: Optional[str] = None
    bio: Optional[str] = None
    certification: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoachAthleteAssign(BaseModel):
    athlete_id: int
