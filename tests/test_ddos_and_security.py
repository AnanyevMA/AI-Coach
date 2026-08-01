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
from app.core.config import settings
from app.core.rate_limiter import rate_limiter_storage, RateLimiter
from app.core.security import encrypt_sensitive_data, decrypt_sensitive_data, AES256GCMCipher
from app.services.ai_coach_engine import ai_coach_engine
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
    await rate_limiter_storage.reset()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    fastapi_app.dependency_overrides.clear()
    await rate_limiter_storage.reset()


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient):
    reg_payload = {
        "email": "ddos_test_user@example.com",
        "password": "Password123!",
        "full_name": "Тестовый Защищенный Атлет",
        "role": "athlete"
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201

    login_res = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "ddos_test_user@example.com", "password": "Password123!"}
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestDDoSAndRateLimitingProtection:
    @pytest.mark.asyncio
    async def test_ai_coach_generate_plan_rate_limiting(self, async_client: AsyncClient, auth_headers: dict):
        """Verify that exceeding AI Coach plan generation rate limit returns HTTP 429 to protect AI tokens."""
        payload = {
            "original_activity_type": "RUNNING",
            "target_duration_minutes": 45,
            "target_hr_zone": "Z2_ENDURANCE",
            "force_offline_fallback": True
        }

        # Send max allowed requests
        for i in range(settings.AI_COACH_RATE_LIMIT_PLAN):
            res = await async_client.post("/api/v1/ai-coach/generate-plan", json=payload, headers=auth_headers)
            assert res.status_code == 200, f"Request {i+1} failed unexpectedly with status {res.status_code}"

        # Excessive request should be rate-limited (HTTP 429)
        blocked_res = await async_client.post("/api/v1/ai-coach/generate-plan", json=payload, headers=auth_headers)
        assert blocked_res.status_code == 429
        data = blocked_res.json()
        assert "Rate limit exceeded" in data["detail"]
        assert "Retry-After" in blocked_res.headers

    @pytest.mark.asyncio
    async def test_ai_coach_analyze_activity_rate_limiting(self, async_client: AsyncClient, auth_headers: dict):
        """Verify that activity analysis endpoint is rate-limited against DDoS."""
        payload = {
            "duration_seconds": 1800,
            "avg_hr": 140,
            "max_hr": 160,
            "rpe_score": 5
        }

        for i in range(settings.AI_COACH_RATE_LIMIT_ANALYZE):
            res = await async_client.post("/api/v1/ai-coach/analyze-activity", json=payload, headers=auth_headers)
            assert res.status_code == 200

        blocked_res = await async_client.post("/api/v1/ai-coach/analyze-activity", json=payload, headers=auth_headers)
        assert blocked_res.status_code == 429

    @pytest.mark.asyncio
    async def test_telemetry_upload_fit_rate_limiting(self, async_client: AsyncClient, auth_headers: dict):
        """Verify that binary FIT upload endpoint is rate-limited against resource exhaustion."""
        fit_bytes = fit_parser_service.create_mock_fit_binary(num_records=5)

        for i in range(settings.TELEMETRY_RATE_LIMIT_UPLOAD_FIT):
            files = {"file": (f"test_{i}.fit", io.BytesIO(fit_bytes), "application/octet-stream")}
            res = await async_client.post("/api/v1/telemetry/upload-fit", files=files, headers=auth_headers)
            assert res.status_code == 201

        files = {"file": ("excess.fit", io.BytesIO(fit_bytes), "application/octet-stream")}
        blocked_res = await async_client.post("/api/v1/telemetry/upload-fit", files=files, headers=auth_headers)
        assert blocked_res.status_code == 429


class TestGeminiKeyProtectionAndAES256Transmission:
    def test_gemini_key_masking(self):
        """Verify Gemini API key masking prevents exposing sensitive credentials."""
        assert ai_coach_engine.mask_api_key("AIzaSy1234567890abcdef") == "AIza...cdef"
        assert ai_coach_engine.mask_api_key("short") == "****"
        assert ai_coach_engine.mask_api_key(None) == "NOT_SET" or ai_coach_engine.mask_api_key(None) != ""

    def test_settings_masked_gemini_key(self):
        """Verify settings helper returns safe masked string."""
        masked = settings.get_masked_gemini_key()
        assert "..." in masked or masked == "****" or masked == "NOT_SET"

    def test_aes256_gcm_transmission_encryption(self):
        """Verify AES-256 encrypted payload structure and decryption integrity."""
        raw_telemetry = '{"heart_rate": 165, "power": 250.5, "spo2": 98}'
        encrypted_json = encrypt_sensitive_data(raw_telemetry)

        assert encrypted_json is not None
        assert "nonce" in encrypted_json
        assert "ciphertext" in encrypted_json

        decrypted = decrypt_sensitive_data(encrypted_json)
        assert decrypted == raw_telemetry
