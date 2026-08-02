"""
strava_service.py — Интеграция Strava API v3 для AI Adaptive Coach v7.1

Компоненты:
- StravaOAuthService: OAuth 2.0 flow (exchange code → tokens, refresh, revoke)
- StravaActivityFetcher: получение деталей тренировки через API v3
- StravaActivityNormalizer: нормализация данных Strava → модель Activity
- StravaWebhookValidator: верификация HMAC-SHA256 подписи входящих событий

Безопасность (P1):
- Access/refresh tokens хранятся зашифрованными (AES-256-GCM)
- OAuth state — CSRF-защита (random, хранится в Redis TTL=5min)
- Логирование: никогда не логируем токены в открытом виде

Обработка Strava-специфики:
- event_type=create: delayed fetch через 1 час (даёт время на корректировки)
- event_type=update: обновляем существующую запись в БД
- Дубликаты: UniqueConstraint(athlete_id, strava_activity_id)
- Аномальный ЧСС: запрос пользователю о сбое датчика, не немедленный Red Flag
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.security import encrypt_sensitive_data, decrypt_sensitive_data

logger = logging.getLogger("strava_service")

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"
STRAVA_SCOPE = "activity:read_all"  # Минимально необходимые права (P2 Legal)

# Порог аномального ЧСС (% от max_hr) для запроса о сбое датчика
ABNORMAL_HR_THRESHOLD_PCT = 1.10  # > 110% от max_hr или > 210 абсолютно


class StravaOAuthService:
    """
    OAuth 2.0 Authorization Code Flow для Strava.
    Использует CSRF-state, шифрует токены перед сохранением в БД.
    """

    def build_authorization_url(self, state: str) -> str:
        """Строит URL для редиректа пользователя на страницу авторизации Strava."""
        params = (
            f"client_id={settings.STRAVA_CLIENT_ID}"
            f"&redirect_uri={settings.STRAVA_REDIRECT_URI}"
            f"&response_type=code"
            f"&scope={STRAVA_SCOPE}"
            f"&state={state}"
            f"&approval_prompt=auto"
        )
        return f"{STRAVA_AUTH_URL}?{params}"

    def generate_csrf_state(self) -> str:
        """Генерирует случайный CSRF state для OAuth (хранится в Redis TTL=5min)."""
        return secrets.token_urlsafe(32)

    async def exchange_code_for_tokens(
        self, code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Обменивает authorization code на access/refresh tokens.
        Возвращает dict с токенами или None при ошибке.
        Токены НИКОГДА не логируются.
        """
        if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
            logger.error("STRAVA_CLIENT_ID или STRAVA_CLIENT_SECRET не заданы в .env")
            return None

        payload = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(STRAVA_TOKEN_URL, data=payload)
                if resp.status_code != 200:
                    logger.error(f"Strava token exchange error {resp.status_code}: {resp.text[:200]}")
                    return None
                data = resp.json()
                logger.info(
                    f"Strava token exchange success: athlete_id={data.get('athlete', {}).get('id')}"
                )
                return data
        except Exception as exc:
            logger.error(f"Strava token exchange exception: {exc}")
            return None

    async def refresh_access_token(
        self, refresh_token_encrypted: str
    ) -> Optional[Dict[str, Any]]:
        """Обновляет access_token по refresh_token. Токен дешифруется только в памяти."""
        if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
            return None

        try:
            refresh_token = decrypt_sensitive_data(refresh_token_encrypted)
        except Exception:
            logger.error("Не удалось дешифровать strava_refresh_token")
            return None

        payload = {
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(STRAVA_TOKEN_URL, data=payload)
                if resp.status_code != 200:
                    logger.error(f"Strava token refresh error {resp.status_code}")
                    return None
                return resp.json()
        except Exception as exc:
            logger.error(f"Strava token refresh exception: {exc}")
            return None

    async def deauthorize(self, access_token_encrypted: str) -> bool:
        """
        Отзывает доступ приложения к аккаунту Strava.
        Вызывается при disconnect (право на удаление, 152-ФЗ).
        """
        try:
            token = decrypt_sensitive_data(access_token_encrypted)
        except Exception:
            logger.error("Не удалось дешифровать access_token при deauthorize")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    STRAVA_DEAUTH_URL,
                    data={"access_token": token}
                )
                if resp.status_code == 200:
                    logger.info("Strava deauthorize: успешно")
                    return True
                logger.warning(f"Strava deauthorize: {resp.status_code}")
                return False
        except Exception as exc:
            logger.error(f"Strava deauthorize exception: {exc}")
            return False

    def encrypt_token(self, token: str) -> str:
        """Шифрует токен Strava перед сохранением в БД (AES-256-GCM)."""
        return encrypt_sensitive_data(token)

    def extract_athlete_tokens(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Извлекает и шифрует токены из ответа Strava.
        Возвращает dict с зашифрованными значениями для сохранения в AthleteProfile.
        """
        expires_at_ts = token_data.get("expires_at", 0)
        expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc) if expires_at_ts else None

        return {
            "strava_athlete_id": token_data.get("athlete", {}).get("id"),
            "strava_access_token_encrypted": self.encrypt_token(token_data.get("access_token", "")),
            "strava_refresh_token_encrypted": self.encrypt_token(token_data.get("refresh_token", "")),
            "strava_token_expires_at": expires_at,
            "strava_scope": token_data.get("scope", STRAVA_SCOPE),
        }


class StravaActivityFetcher:
    """
    Загружает данные конкретной тренировки из Strava API v3.
    Автоматически обновляет истёкший access_token.
    """

    async def _get_valid_access_token(
        self,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        token_expires_at: Optional[datetime],
    ) -> Optional[str]:
        """Возвращает действующий access_token (обновляет если истёк)."""
        now = datetime.now(timezone.utc)

        # Проверяем, не истёк ли токен
        if token_expires_at and token_expires_at > now + timedelta(minutes=5):
            try:
                return decrypt_sensitive_data(access_token_encrypted)
            except Exception:
                pass

        # Обновляем токен
        oauth = StravaOAuthService()
        refreshed = await oauth.refresh_access_token(refresh_token_encrypted)
        if not refreshed:
            logger.error("Не удалось обновить Strava access_token")
            return None

        return refreshed.get("access_token")

    async def fetch_activity(
        self,
        strava_activity_id: int,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        token_expires_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Загружает детали тренировки из Strava API v3.
        Включает ЧСС, мощность, дистанцию, тип спорта.
        Токен никогда не логируется.
        """
        token = await self._get_valid_access_token(
            access_token_encrypted, refresh_token_encrypted, token_expires_at
        )
        if not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{STRAVA_API_BASE}/activities/{strava_activity_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info(f"Strava activity {strava_activity_id} загружена: '{data.get('name')}'")
                    return data
                logger.error(f"Strava activity fetch error {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as exc:
            logger.error(f"Strava activity fetch exception: {exc}")
            return None


class StravaActivityNormalizer:
    """
    Нормализует данные тренировки из Strava API → модель Activity.
    Определяет аномальный ЧСС для запроса у пользователя о сбое датчика.
    """

    # Маппинг типов активностей Strava → наши типы
    SPORT_TYPE_MAP = {
        "Run": "running",
        "VirtualRun": "running",
        "TrailRun": "running",
        "Ride": "cycling",
        "VirtualRide": "cycling",
        "MountainBikeRide": "cycling",
        "Swim": "swimming",
        "Workout": "strength",
        "WeightTraining": "strength",
        "Crossfit": "strength",
        "Walk": "walking",
        "Hike": "hiking",
        "Skiing": "skiing",
        "Rowing": "rowing",
    }

    def normalize(
        self,
        strava_data: Dict[str, Any],
        athlete_id: int,
        athlete_max_hr: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Нормализует ответ Strava API в dict для создания/обновления Activity.
        Также возвращает флаг и значение аномального ЧСС если есть.
        """
        sport_type_raw = strava_data.get("sport_type") or strava_data.get("type", "Workout")
        activity_type = self.SPORT_TYPE_MAP.get(sport_type_raw, "other")

        start_date_str = strava_data.get("start_date") or strava_data.get("start_date_local")
        try:
            if start_date_str:
                start_time = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            else:
                start_time = datetime.now(timezone.utc)
        except (TypeError, ValueError):
            start_time = datetime.now(timezone.utc)

        max_hr = strava_data.get("max_heartrate")
        avg_hr_raw = strava_data.get("average_heartrate")
        avg_hr = int(avg_hr_raw) if avg_hr_raw else None

        distance_m = strava_data.get("distance", 0.0)  # Strava отдаёт в метрах
        duration_s = int(strava_data.get("moving_time") or strava_data.get("elapsed_time") or 0)
        elevation = strava_data.get("total_elevation_gain")

        # Проверка аномального ЧСС
        hr_anomaly = self._check_hr_anomaly(max_hr, athlete_max_hr)

        return {
            "athlete_id": athlete_id,
            "title": strava_data.get("name", "Strava Activity"),
            "activity_type": activity_type,
            "start_time": start_time,
            "duration_seconds": duration_s,
            "distance_meters": float(distance_m) if distance_m else None,
            "avg_hr": avg_hr,
            "max_hr": int(max_hr) if max_hr else None,
            "total_elevation_gain": float(elevation) if elevation else None,
            "source": "strava",
            "strava_activity_id": strava_data.get("id"),
            "strava_fetched_at": datetime.now(timezone.utc),
            # Флаг для принятия решения о Red Flag / sensor check
            "_hr_anomaly": hr_anomaly,
            "_max_hr_value": int(max_hr) if max_hr else None,
        }

    def _check_hr_anomaly(
        self,
        max_hr: Optional[float],
        athlete_max_hr: Optional[int],
    ) -> bool:
        """
        Определяет, является ли ЧСС аномально высоким.
        True если > 210 bpm абсолютно или > 110% от max_hr атлета.
        """
        if max_hr is None:
            return False
        if max_hr >= 210:
            return True
        if athlete_max_hr and max_hr > athlete_max_hr * ABNORMAL_HR_THRESHOLD_PCT:
            return True
        return False


class StravaWebhookValidator:
    """
    Верификация HMAC-SHA256 подписи входящих Strava webhook событий.
    Требование P1 (security_policy_keeper).
    """

    @staticmethod
    def verify_webhook_signature(
        payload_body: bytes,
        signature_header: str,
        client_secret: str,
    ) -> bool:
        """
        Проверяет подпись X-Hub-Signature заголовка.
        Strava подписывает body с помощью HMAC-SHA256 и client_secret.
        """
        if not signature_header.startswith("sha256="):
            return False

        expected_sig = signature_header[len("sha256="):]
        computed = hmac.new(
            client_secret.encode(),
            payload_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed, expected_sig)

    @staticmethod
    def is_valid_challenge(hub_challenge: str, verify_token: str, request_verify_token: str) -> bool:
        """Верификационный challenge при подписке на Strava webhook."""
        return request_verify_token == verify_token


# Глобальные синглтоны
strava_oauth_service = StravaOAuthService()
strava_activity_fetcher = StravaActivityFetcher()
strava_normalizer = StravaActivityNormalizer()
strava_webhook_validator = StravaWebhookValidator()
