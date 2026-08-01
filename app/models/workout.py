from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import AthleteProfile, CoachProfile, User
    from app.models.telemetry import Activity


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    coach_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("coach_profiles.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    target_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    target_hr_zone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="planned", nullable=False)  # planned, completed, skipped, modified, locked
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="workout_plans")


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workout_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workout_plans.id", ondelete="SET NULL"), nullable=True
    )
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    activity_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rpe_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1 to 10 scale
    athlete_feedback: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="workout_sessions")
    red_flags: Mapped[list["RedFlagLog"]] = relationship("RedFlagLog", back_populates="workout_session")


class RedFlagLog(Base):
    __tablename__ = "red_flag_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workout_session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True
    )
    
    # Levels: LEVEL_1_EMERGENCY, LEVEL_2_MEDICAL, LEVEL_3_CAUTION
    level: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trigger_condition: Mapped[str] = mapped_column(String(512), nullable=False)
    action_taken: Mapped[str] = mapped_column(String(512), nullable=False)
    
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="red_flag_logs")
    workout_session: Mapped[Optional["WorkoutSession"]] = relationship("WorkoutSession", back_populates="red_flags")
