"""
tests/test_notification_service.py
Тесты сервиса push-уведомлений (TelegramNotificationService).
AI Adaptive Coach v7.1
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_service():
    """Инстанс TelegramNotificationService с mock-токеном (не делает реальных запросов)."""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "mock_bot_token_777"
        mock_settings.TELEGRAM_WEBAPP_URL = "http://localhost:8000/pwa"
        from app.services.notification_service import TelegramNotificationService
        svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    return svc


# ─── Tests: encrypt / decrypt chat_id ────────────────────────────────────────

def test_encrypt_decrypt_chat_id():
    """chat_id корректно шифруется и дешифруется."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")

    original_id = 123456789
    encrypted = svc.encrypt_chat_id(original_id)
    assert encrypted != str(original_id), "chat_id не должен храниться в открытом виде"

    decrypted = svc.decrypt_chat_id(encrypted)
    assert decrypted == original_id, "Дешифрованный chat_id должен совпадать с оригиналом"


def test_decrypt_invalid_chat_id():
    """Некорректный зашифрованный chat_id возвращает None."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    result = svc.decrypt_chat_id("invalid_garbage_data")
    assert result is None


# ─── Tests: send_message (mock mode) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_message_mock_token():
    """В режиме mock-токена send_message возвращает True без HTTP-запроса."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    result = await svc.send_message(chat_id=123456, text="Test message")
    assert result is True


@pytest.mark.asyncio
async def test_send_message_real_token_api_error():
    """При ошибке API send_message возвращает False, не падает."""
    import httpx
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="real_fake_token_xyz")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client_cls.return_value = mock_client

        result = await svc.send_message(chat_id=123456, text="Test")
    assert result is False


# ─── Tests: notification types ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_morning_checkin():
    """send_morning_checkin в mock-режиме возвращает True."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    result = await svc.send_morning_checkin(chat_id=100, athlete_name="Алексей")
    assert result is True


@pytest.mark.asyncio
async def test_send_workout_ready():
    """send_workout_ready в mock-режиме возвращает True."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    result = await svc.send_workout_ready(
        chat_id=100, workout_type="Интервальный бег", readiness_score=88
    )
    assert result is True


@pytest.mark.asyncio
async def test_send_red_flag_alert_level1():
    """Red Flag Level 1 уведомление содержит экстренные инструкции."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")

    sent_texts = []
    async def capture_send(chat_id, text, reply_markup=None, parse_mode="Markdown"):
        sent_texts.append(text)
        return True

    svc.send_message = capture_send  # type: ignore
    await svc.send_red_flag_alert(
        chat_id=100,
        level="LEVEL_1_EMERGENCY",
        trigger_condition="HR >= 220 bpm",
        is_athlete=True,
    )
    assert any("112" in t or "экстренн" in t.lower() for t in sent_texts), \
        "Level 1 уведомление должно содержать номер экстренной службы"


@pytest.mark.asyncio
async def test_send_weekly_summary():
    """send_weekly_summary в mock-режиме возвращает True."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")
    result = await svc.send_weekly_summary(
        chat_id=100,
        athlete_name="Тест",
        workouts_count=5,
        acwr=1.1,
        hrv_trend="↑ +5%",
    )
    assert result is True


@pytest.mark.asyncio
async def test_send_strava_hr_sensor_check():
    """HR sensor check содержит кнопки выбора причины аномального пульса."""
    from app.services.notification_service import TelegramNotificationService
    svc = TelegramNotificationService(bot_token="mock_bot_token_777")

    markups = []
    async def capture_send(chat_id, text, reply_markup=None, parse_mode="Markdown"):
        if reply_markup:
            markups.append(reply_markup)
        return True

    svc.send_message = capture_send  # type: ignore
    await svc.send_strava_hr_sensor_check(
        chat_id=100,
        activity_title="Бег в горах",
        max_hr=215,
        strava_activity_id=999001,
    )

    assert len(markups) > 0, "Должна быть inline_keyboard с вариантами ответа"
    keyboard_flat = str(markups[0])
    assert "hr_sensor_error" in keyboard_flat
    assert "hr_real_data" in keyboard_flat
