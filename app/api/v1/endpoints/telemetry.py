from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_db
from app.core.config import settings
from app.core.rate_limiter import RateLimiter
from app.core.security import encrypt_sensitive_data
from app.models.telemetry import Activity, HRVData, TelemetryRecord
from app.models.user import AthleteProfile
from app.schemas.telemetry import (
    ActivityCreate,
    ActivityOut,
    HRVDataCreate,
    HRVDataOut,
    TelemetryRecordCreate,
    TelemetryRecordOut,
)
from app.services.fit_parser import FitParserError, fit_parser_service
from app.services.red_flag_service import red_flag_service

router = APIRouter()


@router.post(
    "/record",
    response_model=TelemetryRecordOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=settings.TELEMETRY_RATE_LIMIT_RECORD, seconds=60, prefix="telemetry_record"))],
)
async def post_telemetry_record(
    record_in: TelemetryRecordCreate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Ingest real-time telemetry metrics (heart rate, cadence, power, speed, GPS).
    Evaluates acute heart rate safety triggers via Red Flag Service.
    """
    raw_enc = encrypt_sensitive_data(record_in.raw_payload) if record_in.raw_payload else None

    record = TelemetryRecord(
        athlete_id=athlete.id,
        timestamp=record_in.timestamp,
        heart_rate=record_in.heart_rate,
        cadence=record_in.cadence,
        power=record_in.power,
        speed=record_in.speed,
        latitude=record_in.latitude,
        longitude=record_in.longitude,
        altitude=record_in.altitude,
        raw_encrypted_payload=raw_enc,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    if record_in.heart_rate:
        await red_flag_service.evaluate_athlete_status(
            db=db,
            athlete_id=athlete.id,
            current_hr=record_in.heart_rate
        )

    return record


@router.post(
    "/hrv",
    response_model=HRVDataOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=settings.TELEMETRY_RATE_LIMIT_HRV, seconds=60, prefix="telemetry_hrv"))],
)
async def log_hrv_measurement(
    hrv_in: HRVDataCreate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Log morning HRV (rMSSD, SDNN, readiness score). Encrypts raw metrics for 152-FZ.
    Triggers Red Flag Service to check for autonomic fatigue / illness recovery drops.
    """
    raw_enc = encrypt_sensitive_data(hrv_in.raw_metrics) if hrv_in.raw_metrics else None

    hrv_record = HRVData(
        athlete_id=athlete.id,
        measured_at=hrv_in.measured_at,
        rmssd=hrv_in.rmssd,
        sdnn=hrv_in.sdnn,
        pnn50=hrv_in.pnn50,
        readiness_score=hrv_in.readiness_score,
        encrypted_metrics=raw_enc,
    )
    db.add(hrv_record)
    await db.commit()
    await db.refresh(hrv_record)

    await red_flag_service.evaluate_athlete_status(
        db=db,
        athlete_id=athlete.id,
        latest_rmssd=hrv_in.rmssd
    )

    return hrv_record


@router.get("/hrv/latest", response_model=Optional[HRVDataOut])
async def get_latest_hrv(
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve the latest recorded HRV measurement for the current athlete."""
    result = await db.execute(
        select(HRVData)
        .where(HRVData.athlete_id == athlete.id)
        .order_by(HRVData.measured_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/activity", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
async def record_activity(
    activity_in: ActivityCreate,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Log a completed workout activity."""
    act = Activity(
        athlete_id=athlete.id,
        title=activity_in.title,
        activity_type=activity_in.activity_type,
        start_time=activity_in.start_time,
        duration_seconds=activity_in.duration_seconds,
        distance_meters=activity_in.distance_meters,
        avg_hr=activity_in.avg_hr,
        max_hr=activity_in.max_hr,
        total_elevation_gain=activity_in.total_elevation_gain,
        fit_file_path=activity_in.fit_file_path,
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


@router.post(
    "/upload-fit",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=settings.TELEMETRY_RATE_LIMIT_UPLOAD_FIT, seconds=60, prefix="telemetry_upload_fit"))],
)
async def upload_fit_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    activity_type: Optional[str] = Form(None),
    athlete_max_hr: Optional[int] = Form(None),
    athlete_ftp: Optional[float] = Form(None),
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Ingest and parse binary .FIT telemetric file.
    Decodes time-series metrics (HR, Cadence, Power), calculates HR & Power intensity zones,
    saves Activity record to DB, and checks for acute red flags.
    """
    filename = file.filename or "upload.fit"
    if not filename.lower().endswith((".fit", ".binary")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File extension must be .FIT"
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    max_hr = athlete_max_hr or athlete.max_hr or 190
    ftp = athlete_ftp or 250.0

    try:
        parse_res = fit_parser_service.parse_bytes(content, athlete_max_hr=max_hr, athlete_ftp=ftp)
    except FitParserError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"FIT file parsing error: {str(e)}"
        )

    start_ts = parse_res.records[0].timestamp if parse_res.records else datetime.now(timezone.utc)
    dur_sec = int(parse_res.duration_seconds) if parse_res.duration_seconds else 0

    act = Activity(
        athlete_id=athlete.id,
        title=title or filename,
        activity_type=activity_type or "running",
        start_time=start_ts,
        duration_seconds=dur_sec,
        distance_meters=parse_res.total_distance_meters,
        avg_hr=int(parse_res.avg_hr) if parse_res.avg_hr else None,
        max_hr=parse_res.max_hr,
        fit_file_path=f"fit_uploads/{filename}",
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)

    if parse_res.max_hr:
        await red_flag_service.evaluate_athlete_status(
            db=db,
            athlete_id=athlete.id,
            current_hr=parse_res.max_hr
        )

    return {
        "activity_id": act.id,
        "athlete_id": athlete.id,
        "title": act.title,
        "activity_type": act.activity_type,
        "start_time": act.start_time,
        "duration_seconds": act.duration_seconds,
        "distance_meters": act.distance_meters,
        "avg_hr": act.avg_hr,
        "max_hr": act.max_hr,
        "avg_cadence": parse_res.avg_cadence,
        "max_cadence": parse_res.max_cadence,
        "avg_power": parse_res.avg_power,
        "max_power": parse_res.max_power,
        "records_count": len(parse_res.records),
        "hr_zone_distribution": parse_res.hr_zone_distribution,
        "power_zone_distribution": parse_res.power_zone_distribution,
    }
