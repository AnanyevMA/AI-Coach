from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.telemetry import TelemetryRecord, Activity, HRVData
    from app.models.workout import WorkoutPlan, WorkoutSession, RedFlagLog
    from app.models.audit import ConsentLog


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # PII encrypted fields under 152-FZ
    full_name_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    phone_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    role: Mapped[str] = mapped_column(String(50), default="athlete", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    athlete_profile: Mapped[Optional["AthleteProfile"]] = relationship(
        "AthleteProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    coach_profile: Mapped[Optional["CoachProfile"]] = relationship(
        "CoachProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    consent_logs: Mapped[List["ConsentLog"]] = relationship(
        "ConsentLog", back_populates="user", cascade="all, delete-orphan"
    )


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rest_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Health PII Encrypted under 152-FZ
    medical_notes_encrypted: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="athlete_profile")
    telemetry_records: Mapped[List["TelemetryRecord"]] = relationship(
        "TelemetryRecord", back_populates="athlete", cascade="all, delete-orphan"
    )
    activities: Mapped[List["Activity"]] = relationship(
        "Activity", back_populates="athlete", cascade="all, delete-orphan"
    )
    hrv_data: Mapped[List["HRVData"]] = relationship(
        "HRVData", back_populates="athlete", cascade="all, delete-orphan"
    )
    workout_plans: Mapped[List["WorkoutPlan"]] = relationship(
        "WorkoutPlan", back_populates="athlete", cascade="all, delete-orphan"
    )
    workout_sessions: Mapped[List["WorkoutSession"]] = relationship(
        "WorkoutSession", back_populates="athlete", cascade="all, delete-orphan"
    )
    red_flag_logs: Mapped[List["RedFlagLog"]] = relationship(
        "RedFlagLog", back_populates="athlete", cascade="all, delete-orphan"
    )


class CoachProfile(Base):
    __tablename__ = "coach_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    specialization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    certification: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="coach_profile")
    coach_relations: Mapped[List["CoachAthleteRelation"]] = relationship(
        "CoachAthleteRelation", back_populates="coach", cascade="all, delete-orphan"
    )


class CoachAthleteRelation(Base):
    __tablename__ = "coach_athlete_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    coach_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("coach_profiles.id", ondelete="CASCADE"), nullable=False
    )
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    coach: Mapped["CoachProfile"] = relationship("CoachProfile", back_populates="coach_relations")
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile")
