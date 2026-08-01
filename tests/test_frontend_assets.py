import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def async_client():
    """Async HTTP Client fixture for testing FastAPI static routes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


class TestFrontendAssetsSuite:
    """Test suite for FastAPI static route mounting and HTML/CSS/JS frontend asset delivery."""

    # =========================================================================
    # PWA ATHLETE STATIC ROUTE TESTS (/pwa)
    # =========================================================================
    @pytest.mark.asyncio
    async def test_pwa_route_status_200(self, async_client: AsyncClient):
        """Verify GET /pwa returns HTTP 200 OK."""
        response = await async_client.get("/pwa")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pwa_trailing_slash_status_200(self, async_client: AsyncClient):
        """Verify GET /pwa/ returns HTTP 200 OK."""
        response = await async_client.get("/pwa/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pwa_index_html_status_200(self, async_client: AsyncClient):
        """Verify GET /pwa/index.html returns HTTP 200 OK."""
        response = await async_client.get("/pwa/index.html")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pwa_content_type_html(self, async_client: AsyncClient):
        """Verify /pwa response Content-Type header is text/html."""
        response = await async_client.get("/pwa")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    @pytest.mark.asyncio
    async def test_pwa_html_content_integrity(self, async_client: AsyncClient):
        """Verify /pwa HTML payload contains required tags, title, and athlete PWA UI elements."""
        response = await async_client.get("/pwa")
        assert response.status_code == 200
        html = response.text

        # Validate standard HTML structure
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
        assert "<html" in html
        assert "</html>" in html
        assert "<body" in html
        assert "</body>" in html

        # Validate PWA Athlete application specific keywords
        assert "AI Adaptive Coach" in html
        assert "Check-in" in html or "Readiness" in html or "HRV" in html

    # =========================================================================
    # B2B COACH DASHBOARD STATIC ROUTE TESTS (/coach)
    # =========================================================================
    @pytest.mark.asyncio
    async def test_coach_route_status_200(self, async_client: AsyncClient):
        """Verify GET /coach returns HTTP 200 OK."""
        response = await async_client.get("/coach")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_coach_trailing_slash_status_200(self, async_client: AsyncClient):
        """Verify GET /coach/ returns HTTP 200 OK."""
        response = await async_client.get("/coach/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_coach_index_html_status_200(self, async_client: AsyncClient):
        """Verify GET /coach/index.html returns HTTP 200 OK."""
        response = await async_client.get("/coach/index.html")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_coach_content_type_html(self, async_client: AsyncClient):
        """Verify /coach response Content-Type header is text/html."""
        response = await async_client.get("/coach")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    @pytest.mark.asyncio
    async def test_coach_html_content_integrity(self, async_client: AsyncClient):
        """Verify /coach HTML payload contains required tags, title, and B2B Coach Dashboard elements."""
        response = await async_client.get("/coach")
        assert response.status_code == 200
        html = response.text

        # Validate standard HTML structure
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
        assert "<html" in html
        assert "</html>" in html
        assert "<body" in html
        assert "</body>" in html

        # Validate B2B Coach Portal specific keywords
        assert "Coach" in html or "Тренера" in html
        assert "Heatmap" in html or "Matrix" in html or "Readiness" in html

    # =========================================================================
    # FILE SYSTEM INTEGRITY TESTS
    # =========================================================================
    def test_pwa_file_exists_on_disk(self):
        """Verify frontend/pwa_athlete/index.html file exists and has non-zero size."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        pwa_file = os.path.join(base_dir, "frontend", "pwa_athlete", "index.html")
        assert os.path.exists(pwa_file), f"File {pwa_file} does not exist"
        assert os.path.getsize(pwa_file) > 100, f"File {pwa_file} is suspiciously small"

    def test_coach_file_exists_on_disk(self):
        """Verify frontend/coach/index.html or frontend/b2b_coach/index.html exists and is non-empty."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        coach_file_1 = os.path.join(base_dir, "frontend", "coach", "index.html")
        coach_file_2 = os.path.join(base_dir, "frontend", "b2b_coach", "index.html")

        exists = os.path.exists(coach_file_1) or os.path.exists(coach_file_2)
        assert exists, "Neither frontend/coach/index.html nor frontend/b2b_coach/index.html exists"

        if os.path.exists(coach_file_1):
            assert os.path.getsize(coach_file_1) > 100
        if os.path.exists(coach_file_2):
            assert os.path.getsize(coach_file_2) > 100
