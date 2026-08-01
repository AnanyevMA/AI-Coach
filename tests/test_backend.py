import asyncio
import pytest
from datetime import datetime, timezone, date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.core.security import (
    encrypt_sensitive_data,
    decrypt_sensitive_data,
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.db.base import Base
from app.models.user import User, AthleteProfile, CoachProfile, CoachAthleteRelation
from app.models.telemetry import TelemetryRecord, Activity, HRVData
from app.models.workout import WorkoutPlan, WorkoutSession, RedFlagLog
from app.models.audit import ConsentLog
from app.services.red_flag_service import red_flag_service


async def run_backend_verification():
    print("\n--- 1. Testing Core Security & 152-FZ Encryption ---")
    secret_text = "Иванов Иван Иванович, +7 (999) 000-00-00, Жалобы: боли в колене"
    enc = encrypt_sensitive_data(secret_text)
    dec = decrypt_sensitive_data(enc)
    print(f"Original Text:  {secret_text}")
    print(f"Encrypted Text: {enc}")
    print(f"Decrypted Text: {dec}")
    assert secret_text == dec, "Encryption/Decryption mismatch!"
    print("✅ 152-FZ AES-256-GCM Encryption verified!")

    pwd = "SecretPassword123!"
    hashed = get_password_hash(pwd)
    assert verify_password(pwd, hashed), "Password verification failed!"
    print("✅ Password hashing verified!")

    token = create_access_token(subject="123", extra_claims={"role": "athlete"})
    payload = decode_access_token(token)
    assert payload and payload.get("sub") == "123", "JWT decoding failed!"
    print("✅ JWT token generation verified!")

    print("\n--- 2. Testing Database Models & Async Session ---")
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database schema creation verified!")

    async with async_session() as db:
        # Create User & Athlete Profile
        user = User(
            email="athlete@example.com",
            hashed_password=hashed,
            full_name_encrypted=encrypt_sensitive_data("Тестовый Атлет"),
            phone_encrypted=encrypt_sensitive_data("+79001234567"),
            role="athlete",
        )
        db.add(user)
        await db.flush()

        athlete = AthleteProfile(
            user_id=user.id,
            max_hr=190,
            rest_hr=55,
            medical_notes_encrypted=encrypt_sensitive_data("Аллергических реакций нет")
        )
        db.add(athlete)

        # Log Consent
        consent = ConsentLog(
            user_id=user.id,
            consent_type="personal_data_processing",
            is_granted=True,
            legal_document_version="v1.0"
        )
        db.add(consent)
        await db.commit()
        await db.refresh(athlete)
        print(f"✅ Created User (ID: {user.id}) & Athlete Profile (ID: {athlete.id})")

        print("\n--- 3. Testing Red Flag Triage Engine ---")
        # Test Level 1 Emergency
        t1 = await red_flag_service.evaluate_athlete_status(
            db=db,
            athlete_id=athlete.id,
            current_hr=215,
            symptoms_text="Severe chest pain reported"
        )
        print(f"Level 1 Result: Triggered={t1.flag_triggered}, Level={t1.level}, Action={t1.action_taken}")
        assert t1.level == red_flag_service.LEVEL_1_EMERGENCY, "Level 1 Emergency expected!"

        # Test Level 2 Medical Lock
        t2 = await red_flag_service.evaluate_athlete_status(
            db=db,
            athlete_id=athlete.id,
            latest_rmssd=25.0,  # 50% drop from baseline 50ms
            baseline_rmssd=50.0
        )
        print(f"Level 2 Result: Triggered={t2.flag_triggered}, Level={t2.level}, Action={t2.action_taken}")
        assert t2.level == red_flag_service.LEVEL_2_MEDICAL, "Level 2 Medical expected!"

        # Test Level 3 Caution Reset
        t3 = await red_flag_service.evaluate_athlete_status(
            db=db,
            athlete_id=athlete.id,
            rpe_score=8,
            latest_rmssd=40.0,  # 20% drop
            baseline_rmssd=50.0
        )
        print(f"Level 3 Result: Triggered={t3.flag_triggered}, Level={t3.level}, Action={t3.action_taken}")
        assert t3.level == red_flag_service.LEVEL_3_CAUTION, "Level 3 Caution expected!"

        print("✅ Red Flag Triage Engine successfully verified all 3 risk levels!")

    await test_engine.dispose()
    print("\n🎉 ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_backend_verification())
