"""
test_phase5_enhancements.py — Pytest suite for Phase 5.1 Telemetry Downsampling & Direct Wearable Webhooks
AI Adaptive Coach v7.0
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.telemetry_analysis_service import telemetry_analysis_service


def test_telemetry_downsampling():
    """Test telemetry time series downsampling for token burn optimization."""
    raw_series = [140.0 + (i % 10) for i in range(100)]  # 100 Hz/sec readings
    downsampled = telemetry_analysis_service.downsample_telemetry_series(raw_series, window_size=10)
    
    assert len(downsampled) == 10
    assert isinstance(downsampled[0], float)
    assert 140.0 <= downsampled[0] <= 150.0


@pytest.mark.asyncio
async def test_garmin_webhook_endpoint():
    """Test Garmin Connect direct webhook endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/webhooks/garmin",
            json={"user_id": "athlete_123", "activities": [{"hr": 145, "duration": 3600}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "garmin_connect"
    assert data["compliance_152_fz_encrypted"] is True


@pytest.mark.asyncio
async def test_oura_webhook_endpoint():
    """Test Oura Ring direct webhook endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/webhooks/oura",
            json={"user_id": "athlete_456", "sleep": [{"rmssd": 54.2, "score": 88}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "oura_ring"


@pytest.mark.asyncio
async def test_whoop_webhook_endpoint():
    """Test Whoop Strap direct webhook endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/webhooks/whoop",
            json={"user_id": "athlete_789", "cycles": [{"recovery_score": 75, "strain": 14.2}]},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "whoop_strap"
