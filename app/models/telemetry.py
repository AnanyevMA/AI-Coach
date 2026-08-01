from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import AthleteProfile


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    heart_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cadence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # 152-FZ encrypted raw telemetry payload if containing sensitive GPS/health traces
    raw_encrypted_payload: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="telemetry_records")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # running, cycling, swimming, etc.
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_elevation_gain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fit_file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="activities")


class HRVData(Base):
    __tablename__ = "hrv_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("athlete_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    rmssd: Mapped[float] = mapped_column(Float, nullable=False)
    sdnn: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnn50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readiness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Encrypted full RR-interval series or detailed metrics per 152-FZ
    encrypted_metrics: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    athlete: Mapped["AthleteProfile"] = relationship("AthleteProfile", back_populates="hrv_data")
