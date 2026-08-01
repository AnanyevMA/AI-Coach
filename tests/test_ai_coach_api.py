import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app as fastapi_app
from app.db.base import Base
import app.models.user  # noqa: F401
import app.models.telemetry  # noqa: F401
import app.models.workout  # noqa: F401
import app.models.audit  # noqa: F401
from app.api.v1.deps import get_db
from app.services.fit_parser import fit_parser_service

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=StaticPool, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def auth_athlete_headers(async_client: AsyncClient):
    reg_payload = {
        "email": "ai_coach_athlete@example.com",
        "password": "Password123!",
        "full_name": "Тестовый Атлет",
        "role": "athlete"
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201

    login_res = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "ai_coach_athlete@example.com", "password": "Password123!"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAICoachEndpoints:
    @pytest.mark.asyncio
    async def test_generate_plan_level0_success(self, async_client: AsyncClient, auth_athlete_headers: dict):
        payload = {
            "original_activity_type": "RUNNING",
            "target_duration_minutes": 60,
            "target_hr_zone": "Z3_TEMPO",
            "goal": "Marathon Speed",
            "force_offline_fallback": True
        }
        res = await async_client.post("/api/v1/ai-coach/generate-plan", json=payload, headers=auth_athlete_headers)
        assert res.status_code == 200

        data = res.json()
        assert "plan_title" in data
        assert data["total_duration_minutes"] == 60
        assert data["target_hr_zone"] == "Z3_TEMPO"
        assert data["safety_assessment"]["is_safe"] is True

    @pytest.mark.asyncio
    async def test_generate_plan_red_flag_blocked(self, async_client: AsyncClient, auth_athlete_headers: dict):
        payload = {
            "chest_pain_or_pressure": True,
            "original_activity_type": "RUNNING",
            "target_duration_minutes": 60
        }
        res = await async_client.post("/api/v1/ai-coach/generate-plan", json=payload, headers=auth_athlete_headers)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert detail["error"] == "RED_FLAG_BLOCKED"
        assert detail["triage_level"] == "LEVEL_1_EMERGENCY"

    @pytest.mark.asyncio
    async def test_analyze_activity_success(self, async_client: AsyncClient, auth_athlete_headers: dict):
        payload = {
            "duration_seconds": 3600,
            "avg_hr": 148,
            "max_hr": 172,
            "rpe_score": 7,
            "athlete_feedback": "Отличная пробежка в темпе"
        }
        res = await async_client.post("/api/v1/ai-coach/analyze-activity", json=payload, headers=auth_athlete_headers)
        assert res.status_code == 200

        data = res.json()
        assert "compliance_score" in data
        assert "coaching_summary" in data

    @pytest.mark.asyncio
    async def test_upload_fit_file_success(self, async_client: AsyncClient, auth_athlete_headers: dict):
        fit_bytes = fit_parser_service.create_mock_fit_binary(
            num_records=15, base_hr=150, base_cadence=90, base_power=220.0
        )

        files = {
            "file": ("test_workout.fit", io.BytesIO(fit_bytes), "application/octet-stream")
        }
        data = {
            "title": "Morning Run FIT",
            "activity_type": "running",
            "athlete_max_hr": 190,
            "athlete_ftp": 250
        }

        res = await async_client.post("/api/v1/telemetry/upload-fit", files=files, data=data, headers=auth_athlete_headers)
        assert res.status_code == 201

        resp_data = res.json()
        assert resp_data["title"] == "Morning Run FIT"
        assert resp_data["records_count"] == 15
        assert resp_data["avg_hr"] is not None
        assert "hr_zone_distribution" in resp_data
        assert "power_zone_distribution" in resp_data
