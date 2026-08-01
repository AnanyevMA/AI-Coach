import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.db.base import Base
from app.api.v1.deps import get_db

# Create isolated in-memory SQLite database engine for async API testing
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
    """Override get_db dependency to use in-memory SQLite session."""
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    """Create database tables before each test and drop them after."""
    app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client():
    """Async HTTP Client fixture for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class TestFastAPIEndpoints:
    """Async test suite for FastAPI endpoints: /health, /metrics, /api/v1/auth/register, /api/v1/athletes, /api/v1/coaches."""

    # =========================================================================
    # /health & /metrics ENDPOINT TESTS
    # =========================================================================
    @pytest.mark.asyncio
    async def test_root_health_endpoint(self, async_client: AsyncClient):
        """Verify root /health returns HTTP 200 and healthy status payload."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    @pytest.mark.asyncio
    async def test_prometheus_metrics_endpoint(self, async_client: AsyncClient):
        """Verify /metrics returns Prometheus text format and OWASP security headers."""
        response = await async_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        assert "http_requests_total" in response.text
        assert "process_uptime_seconds" in response.text
        assert "http_request_duration_seconds" in response.text
        assert "active_sessions_total" in response.text
        # Security Headers
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_api_v1_health_endpoint(self, async_client: AsyncClient):
        """Verify /api/v1/health checks DB connectivity and 152-FZ encryption status."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "online"
        assert data["compliance_152_fz"]["enabled"] is True
        assert data["compliance_152_fz"]["crypto_aes256_gcm"] == "ok"
        assert data["database"] == "ok"

    # =========================================================================
    # /api/v1/auth/register ENDPOINT TESTS
    # =========================================================================
    @pytest.mark.asyncio
    async def test_register_athlete_success(self, async_client: AsyncClient):
        """Verify user registration for athlete role with 152-FZ consent parameters."""
        payload = {
            "email": "athlete_api_test@example.com",
            "password": "SecurePassword123!",
            "full_name": "Алексей Петров",
            "phone": "+79991112233",
            "role": "athlete",
            "consent_personal_data": True,
            "consent_health_data": True,
            "legal_document_version": "v1.0"
        }
        response = await async_client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201
        
        data = response.json()
        assert "id" in data
        assert data["email"] == payload["email"]
        assert data["full_name"] == payload["full_name"]
        assert data["role"] == "athlete"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_register_coach_success(self, async_client: AsyncClient):
        """Verify user registration for coach role."""
        payload = {
            "email": "coach_api_test@example.com",
            "password": "SecureCoachPass123!",
            "full_name": "Сергей Смирнов",
            "phone": "+79992223344",
            "role": "coach",
            "consent_personal_data": True,
            "consent_health_data": True
        }
        response = await async_client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["role"] == "coach"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self, async_client: AsyncClient):
        """Verify duplicate registration returns HTTP 400 Bad Request."""
        payload = {
            "email": "duplicate_api@example.com",
            "password": "Password123!",
            "full_name": "Первый Атлет",
            "role": "athlete"
        }
        # First registration
        res1 = await async_client.post("/api/v1/auth/register", json=payload)
        assert res1.status_code == 201

        # Duplicate attempt
        res2 = await async_client.post("/api/v1/auth/register", json=payload)
        assert res2.status_code == 400
        assert "already exists" in res2.json()["detail"]

    # =========================================================================
    # /api/v1/athletes ENDPOINT TESTS
    # =========================================================================
    @pytest.mark.asyncio
    async def test_athlete_profile_flow(self, async_client: AsyncClient):
        """Verify athlete authentication, profile retrieval, and updating 152-FZ medical notes."""
        # 1. Register athlete
        reg_payload = {
            "email": "athlete_profile_test@example.com",
            "password": "Password123!",
            "full_name": "Иван Иванов",
            "role": "athlete"
        }
        reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201

        # 2. Login to get JWT token
        login_res = await async_client.post(
            "/api/v1/auth/login",
            data={"username": "athlete_profile_test@example.com", "password": "Password123!"}
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Get profile
        profile_res = await async_client.get("/api/v1/athletes/profile", headers=headers)
        assert profile_res.status_code == 200
        assert profile_res.json()["user_id"] == reg_res.json()["id"]

        # 4. Update profile (medical notes encrypted)
        update_payload = {
            "height_cm": 182.5,
            "weight_kg": 76.0,
            "max_hr": 192,
            "rest_hr": 54,
            "medical_notes": "Перенесена травма мениска правого колена в 2024 году."
        }
        update_res = await async_client.put("/api/v1/athletes/profile", json=update_payload, headers=headers)
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["height_cm"] == 182.5
        assert updated_data["weight_kg"] == 76.0
        assert updated_data["medical_notes"] == update_payload["medical_notes"]

    # =========================================================================
    # /api/v1/coaches ENDPOINT TESTS
    # =========================================================================
    @pytest.mark.asyncio
    async def test_coach_profile_and_assignment_flow(self, async_client: AsyncClient):
        """Verify coach profile flow and assigning athletes to coaches."""
        # 1. Register Coach
        coach_reg = await async_client.post("/api/v1/auth/register", json={
            "email": "head_coach@example.com",
            "password": "CoachPassword123!",
            "full_name": "Тренер Главный",
            "role": "coach"
        })
        assert coach_reg.status_code == 201

        # Register Athlete
        athlete_reg = await async_client.post("/api/v1/auth/register", json={
            "email": "trainee@example.com",
            "password": "AthletePassword123!",
            "full_name": "Ученик Спортсмен",
            "role": "athlete"
        })
        assert athlete_reg.status_code == 201

        # 2. Login as Coach
        coach_login = await async_client.post(
            "/api/v1/auth/login",
            data={"username": "head_coach@example.com", "password": "CoachPassword123!"}
        )
        assert coach_login.status_code == 200
        coach_token = coach_login.json()["access_token"]
        coach_headers = {"Authorization": f"Bearer {coach_token}"}

        # 3. Get Coach Profile
        coach_prof_res = await async_client.get("/api/v1/coaches/profile", headers=coach_headers)
        assert coach_prof_res.status_code == 200

        # 4. Update Coach Profile
        update_coach = await async_client.put("/api/v1/coaches/profile", json={
            "specialization": "Триатлон & Марафон",
            "bio": "Мастер спорта по марафону",
            "certification": "ACSM Certified Exercise Physiologist"
        }, headers=coach_headers)
        assert update_coach.status_code == 200
        assert update_coach.json()["specialization"] == "Триатлон & Марафон"

        # 5. Assign Athlete (Athlete profile id = 1 in fresh DB)
        assign_res = await async_client.post(
            "/api/v1/coaches/assign",
            json={"athlete_id": 1},
            headers=coach_headers
        )
        assert assign_res.status_code == 201
        assert assign_res.json()["status"] == "success"

        # 6. List Assigned Athletes for Coach
        assigned_list_res = await async_client.get("/api/v1/coaches/athletes", headers=coach_headers)
        assert assigned_list_res.status_code == 200
        assigned_athletes = assigned_list_res.json()
        assert len(assigned_athletes) == 1
        assert assigned_athletes[0]["id"] == 1
