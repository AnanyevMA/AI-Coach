"""
tests/test_strava_integration.py
Тесты интеграции Strava: OAuth, нормализатор, webhook validator.
AI Adaptive Coach v7.1
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# ─── StravaActivityNormalizer ─────────────────────────────────────────────────

class TestStravaActivityNormalizer:

    @pytest.fixture
    def normalizer(self):
        from app.services.strava_service import StravaActivityNormalizer
        return StravaActivityNormalizer()

    def test_normalize_run_activity(self, normalizer):
        """Тренировка типа Run нормализуется в 'running'."""
        data = {
            "id": 12345,
            "name": "Утренняя пробежка",
            "sport_type": "Run",
            "start_date": "2026-08-01T05:00:00Z",
            "moving_time": 3600,
            "distance": 10000.0,
            "average_heartrate": 145.5,
            "max_heartrate": 172.0,
            "total_elevation_gain": 50.0,
        }
        result = normalizer.normalize(data, athlete_id=1, athlete_max_hr=185)

        assert result["activity_type"] == "running"
        assert result["title"] == "Утренняя пробежка"
        assert result["duration_seconds"] == 3600
        assert result["distance_meters"] == 10000.0
        assert result["avg_hr"] == 145
        assert result["max_hr"] == 172
        assert result["source"] == "strava"
        assert result["strava_activity_id"] == 12345
        assert result["_hr_anomaly"] is False

    def test_normalize_cycling_activity(self, normalizer):
        """VirtualRide нормализуется в 'cycling'."""
        data = {
            "id": 22222,
            "name": "Zwift ride",
            "sport_type": "VirtualRide",
            "start_date": "2026-08-01T08:00:00Z",
            "moving_time": 5400,
            "distance": 40000.0,
            "max_heartrate": 165.0,
        }
        result = normalizer.normalize(data, athlete_id=2)
        assert result["activity_type"] == "cycling"
        assert result["_hr_anomaly"] is False

    def test_normalize_unknown_sport_type(self, normalizer):
        """Неизвестный тип спорта маппируется в 'other'."""
        data = {
            "id": 33333,
            "name": "Необычный спорт",
            "sport_type": "Pickleball",
            "start_date": "2026-08-01T10:00:00Z",
            "moving_time": 1800,
        }
        result = normalizer.normalize(data, athlete_id=3)
        assert result["activity_type"] == "other"

    def test_hr_anomaly_absolute_threshold(self, normalizer):
        """ЧСС >= 210 bpm всегда считается аномальным."""
        data = {
            "id": 44444,
            "name": "Тест пульсометра",
            "sport_type": "Run",
            "start_date": "2026-08-01T06:00:00Z",
            "moving_time": 1800,
            "max_heartrate": 215.0,
        }
        result = normalizer.normalize(data, athlete_id=4, athlete_max_hr=190)
        assert result["_hr_anomaly"] is True
        assert result["_max_hr_value"] == 215

    def test_hr_anomaly_relative_threshold(self, normalizer):
        """ЧСС > 110% max_hr атлета считается аномальным."""
        data = {
            "id": 55555,
            "name": "Горная тренировка",
            "sport_type": "Run",
            "start_date": "2026-08-01T07:00:00Z",
            "moving_time": 2700,
            "max_heartrate": 195.0,  # > 175 * 1.1 = 192.5
        }
        result = normalizer.normalize(data, athlete_id=5, athlete_max_hr=175)
        assert result["_hr_anomaly"] is True

    def test_no_hr_anomaly_normal_data(self, normalizer):
        """Нормальный ЧСС не триггерит аномалию."""
        data = {
            "id": 66666,
            "name": "Лёгкая пробежка",
            "sport_type": "Run",
            "start_date": "2026-08-01T08:00:00Z",
            "moving_time": 2400,
            "max_heartrate": 160.0,
        }
        result = normalizer.normalize(data, athlete_id=6, athlete_max_hr=185)
        assert result["_hr_anomaly"] is False

    def test_missing_start_date_fallback(self, normalizer):
        """При отсутствии даты используется текущее время UTC."""
        data = {
            "id": 77777,
            "name": "Тест без даты",
            "sport_type": "Run",
            "moving_time": 1200,
        }
        result = normalizer.normalize(data, athlete_id=7)
        assert result["start_time"] is not None
        assert isinstance(result["start_time"], datetime)

    def test_distance_in_meters(self, normalizer):
        """Расстояние Strava (в метрах) корректно передаётся."""
        data = {
            "id": 88888,
            "name": "Полумарафон",
            "sport_type": "Run",
            "start_date": "2026-08-01T09:00:00Z",
            "moving_time": 5700,
            "distance": 21097.5,  # 21.1 км в метрах
        }
        result = normalizer.normalize(data, athlete_id=8)
        assert result["distance_meters"] == pytest.approx(21097.5)


# ─── StravaWebhookValidator ────────────────────────────────────────────────────

class TestStravaWebhookValidator:

    @pytest.fixture
    def validator(self):
        from app.services.strava_service import StravaWebhookValidator
        return StravaWebhookValidator()

    def test_valid_hmac_signature(self, validator):
        """Корректная HMAC-SHA256 подпись проходит верификацию."""
        secret = "my_client_secret"
        payload = b'{"object_type": "activity", "aspect_type": "create"}'
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        sig_header = f"sha256={expected}"

        result = validator.verify_webhook_signature(payload, sig_header, secret)
        assert result is True

    def test_invalid_hmac_signature(self, validator):
        """Некорректная подпись отклоняется."""
        secret = "my_client_secret"
        payload = b'{"object_type": "activity"}'
        sig_header = "sha256=invalid_signature_here"

        result = validator.verify_webhook_signature(payload, sig_header, secret)
        assert result is False

    def test_missing_sha256_prefix(self, validator):
        """Подпись без префикса sha256= отклоняется."""
        result = validator.verify_webhook_signature(b"payload", "abcdef123456", "secret")
        assert result is False

    def test_webhook_verify_challenge(self, validator):
        """Корректный verify_token проходит challenge верификацию."""
        result = validator.is_valid_challenge(
            hub_challenge="challenge_value",
            verify_token="my_secret_token",
            request_verify_token="my_secret_token",
        )
        assert result is True

    def test_webhook_verify_challenge_fail(self, validator):
        """Неверный verify_token не проходит."""
        result = validator.is_valid_challenge(
            hub_challenge="challenge_value",
            verify_token="correct_token",
            request_verify_token="wrong_token",
        )
        assert result is False


# ─── StravaOAuthService ───────────────────────────────────────────────────────

class TestStravaOAuthService:

    @pytest.fixture
    def oauth(self):
        from app.services.strava_service import StravaOAuthService
        return StravaOAuthService()

    def test_generate_csrf_state(self, oauth):
        """generate_csrf_state генерирует уникальный токен достаточной длины."""
        state1 = oauth.generate_csrf_state()
        state2 = oauth.generate_csrf_state()
        assert state1 != state2, "CSRF state должен быть уникальным"
        assert len(state1) >= 32

    def test_build_authorization_url(self, oauth):
        """build_authorization_url содержит правильные параметры OAuth."""
        with patch("app.services.strava_service.settings") as ms:
            ms.STRAVA_CLIENT_ID = "test_client_123"
            ms.STRAVA_REDIRECT_URI = "http://localhost:8000/api/v1/strava/callback"
            url = oauth.build_authorization_url(state="test_state_abc")

        assert "strava.com/oauth/authorize" in url
        assert "test_client_123" in url
        assert "activity:read_all" in url
        assert "test_state_abc" in url
        assert "localhost:8000" in url

    def test_extract_athlete_tokens_encrypts(self, oauth):
        """extract_athlete_tokens шифрует токены перед возвратом."""
        token_data = {
            "access_token": "raw_access_token_abc",
            "refresh_token": "raw_refresh_token_xyz",
            "expires_at": 9999999999,
            "scope": "activity:read_all",
            "athlete": {"id": 12345},
        }
        result = oauth.extract_athlete_tokens(token_data)

        assert result["strava_athlete_id"] == 12345
        assert result["strava_access_token_encrypted"] != "raw_access_token_abc", \
            "Access token должен быть зашифрован"
        assert result["strava_refresh_token_encrypted"] != "raw_refresh_token_xyz", \
            "Refresh token должен быть зашифрован"
        assert result["strava_scope"] == "activity:read_all"
        assert result["strava_token_expires_at"] is not None
