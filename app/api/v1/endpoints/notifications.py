"""
notifications.py — REST API для управления настройками push-уведомлений.
AI Adaptive Coach v7.1

Эндпоинты:
  GET  /api/v1/notifications/settings — текущие настройки уведомлений атлета
  PUT  /api/v1/notifications/settings — обновить настройки (время, типы, opt-out)
  POST /api/v1/notifications/test     — отправить тестовое уведомление
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_db
from app.models.user import AthleteProfile
from app.services.notification_service import notification_service

router = APIRouter()
logger = logging.getLogger("notifications_api")


class NotificationSettings(BaseModel):
    """Модель настроек уведомлений атлета."""
    notify_morning_checkin: bool = True
    notify_workout_ready: bool = True
    notify_red_flag: bool = True
    notify_weekly_summary: bool = True
    # Персональное время утреннего чек-ина (UTC)
    notification_checkin_hour_utc: int = Field(default=7, ge=0, le=23)
    notification_checkin_minute_utc: int = Field(default=0, ge=0, le=59)


class NotificationSettingsOut(NotificationSettings):
    """Расширенный ответ с информацией о Telegram привязке."""
    telegram_linked: bool = False
    checkin_time_display: str = "07:00 UTC"


class TestNotificationRequest(BaseModel):
    """Запрос тестового уведомления."""
    notification_type: str = Field(
        default="morning_checkin",
        description="Тип: morning_checkin / workout_ready / weekly_summary"
    )

    @field_validator("notification_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"morning_checkin", "workout_ready", "weekly_summary"}
        if v not in allowed:
            raise ValueError(f"notification_type должен быть одним из: {allowed}")
        return v


@router.get(
    "/settings",
    response_model=NotificationSettingsOut,
    summary="Получить настройки уведомлений",
)
async def get_notification_settings(
    athlete: AthleteProfile = Depends(get_current_athlete),
) -> NotificationSettingsOut:
    """Возвращает текущие настройки push-уведомлений атлета."""
    hour = athlete.notification_checkin_hour_utc
    minute = athlete.notification_checkin_minute_utc

    return NotificationSettingsOut(
        notify_morning_checkin=athlete.notify_morning_checkin,
        notify_workout_ready=athlete.notify_workout_ready,
        notify_red_flag=athlete.notify_red_flag,
        notify_weekly_summary=athlete.notify_weekly_summary,
        notification_checkin_hour_utc=hour,
        notification_checkin_minute_utc=minute,
        telegram_linked=athlete.telegram_chat_id_encrypted is not None,
        checkin_time_display=f"{hour:02d}:{minute:02d} UTC",
    )


@router.put(
    "/settings",
    response_model=NotificationSettingsOut,
    summary="Обновить настройки уведомлений",
)
async def update_notification_settings(
    settings_in: NotificationSettings,
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
) -> NotificationSettingsOut:
    """
    Обновляет настройки push-уведомлений:
    - Включить/выключить каждый тип отдельно (opt-in/opt-out)
    - Установить персональное время утреннего чек-ина (UTC)
    """
    await db.execute(
        update(AthleteProfile)
        .where(AthleteProfile.id == athlete.id)
        .values(
            notify_morning_checkin=settings_in.notify_morning_checkin,
            notify_workout_ready=settings_in.notify_workout_ready,
            notify_red_flag=settings_in.notify_red_flag,
            notify_weekly_summary=settings_in.notify_weekly_summary,
            notification_checkin_hour_utc=settings_in.notification_checkin_hour_utc,
            notification_checkin_minute_utc=settings_in.notification_checkin_minute_utc,
        )
    )
    await db.commit()

    hour = settings_in.notification_checkin_hour_utc
    minute = settings_in.notification_checkin_minute_utc
    logger.info(
        f"Notification settings updated: athlete_id={athlete.id}, "
        f"checkin_time={hour:02d}:{minute:02d} UTC"
    )

    return NotificationSettingsOut(
        **settings_in.model_dump(),
        telegram_linked=athlete.telegram_chat_id_encrypted is not None,
        checkin_time_display=f"{hour:02d}:{minute:02d} UTC",
    )


@router.post(
    "/test",
    summary="Отправить тестовое уведомление",
)
async def send_test_notification(
    request: TestNotificationRequest,
    athlete: AthleteProfile = Depends(get_current_athlete),
) -> dict:
    """
    Отправляет тестовое уведомление указанного типа.
    Требует привязанного Telegram аккаунта (необходимо отправить /start боту).
    """
    if not athlete.telegram_chat_id_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Telegram не привязан. Отправьте команду /start боту @YourBotName, "
                "чтобы зарегистрировать Telegram аккаунт."
            )
        )

    chat_id = notification_service.decrypt_chat_id(athlete.telegram_chat_id_encrypted)
    if chat_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка дешифровки Telegram chat_id. Обратитесь в поддержку."
        )

    success = False
    ntype = request.notification_type

    if ntype == "morning_checkin":
        success = await notification_service.send_morning_checkin(
            chat_id=chat_id,
            athlete_name="тестовый атлет",
        )
    elif ntype == "workout_ready":
        success = await notification_service.send_workout_ready(
            chat_id=chat_id,
            workout_type="5×1000m Темповые Интервалы",
            readiness_score=85,
        )
    elif ntype == "weekly_summary":
        success = await notification_service.send_weekly_summary(
            chat_id=chat_id,
            athlete_name="тестовый атлет",
            workouts_count=4,
            acwr=1.05,
            hrv_trend="↑ +8%",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось отправить уведомление. Проверьте TELEGRAM_BOT_TOKEN."
        )

    logger.info(f"Тестовое уведомление '{ntype}' отправлено: chat_id={chat_id}")
    return {
        "status": "sent",
        "notification_type": ntype,
        "chat_id_masked": f"***{str(chat_id)[-4:]}",
    }
