"""
strava.py — REST API эндпоинты для интеграции Strava.
AI Adaptive Coach v7.1

Эндпоинты:
  GET  /api/v1/strava/auth        — редирект на Strava OAuth (с CSRF state)
  GET  /api/v1/strava/callback    — обработка OAuth callback, сохранение токенов
  GET  /api/v1/strava/webhook     — верификационный challenge при регистрации подписки
  POST /api/v1/strava/webhook     — приём push-событий от Strava (create/update activity)
  DELETE /api/v1/strava/disconnect — отвязка Strava аккаунта (право на удаление токенов)
  GET  /api/v1/strava/status      — статус подключения Strava

Strava-специфика:
  - event_type=create: delayed fetch через STRAVA_FETCH_DELAY_SECONDS (1 час по умолчанию)
  - event_type=update: обновление существующей записи в БД
  - Аномальный ЧСС: send_strava_hr_sensor_check() вместо немедленного Red Flag
"""

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_athlete, get_db
from app.core.config import settings
from app.core.security import decrypt_sensitive_data
from app.models.telemetry import Activity
from app.models.user import AthleteProfile, User
from app.services.notification_service import notification_service
from app.services.notification_scheduler import notification_scheduler
from app.services.strava_service import (
    strava_activity_fetcher,
    strava_normalizer,
    strava_oauth_service,
    strava_webhook_validator,
)

router = APIRouter()
logger = logging.getLogger("strava_api")

# Простое in-memory хранилище CSRF state (для тестов/dev; в prod — Redis)
# Формат: {state: athlete_id}
_oauth_states: dict = {}


# ─── Подключение Strava ──────────────────────────────────────────────────────

@router.get("/auth", summary="Начать OAuth подключение Strava")
async def strava_auth(
    athlete: AthleteProfile = Depends(get_current_athlete),
):
    """
    Перенаправляет пользователя на страницу авторизации Strava.
    Генерирует CSRF state и сохраняет его для верификации в callback.
    """
    if not settings.STRAVA_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Strava интеграция не настроена. Задайте STRAVA_CLIENT_ID в .env."
        )

    csrf_state = strava_oauth_service.generate_csrf_state()
    _oauth_states[csrf_state] = athlete.id  # TTL в Redis в prod

    auth_url = strava_oauth_service.build_authorization_url(state=csrf_state)
    logger.info(f"Strava OAuth redirect: athlete_id={athlete.id}")
    return RedirectResponse(url=auth_url)


@router.get("/callback", summary="OAuth callback от Strava")
async def strava_callback(
    code: str = Query(..., description="Authorization code от Strava"),
    state: str = Query(..., description="CSRF state"),
    error: str = Query(default="", description="Ошибка авторизации"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получает authorization code, обменивает на токены, сохраняет в AthleteProfile.
    Токены шифруются AES-256-GCM перед сохранением (P1).
    """
    if error:
        logger.warning(f"Strava OAuth error: {error}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Strava отклонил авторизацию: {error}"}
        )

    # CSRF верификация
    athlete_id = _oauth_states.pop(state, None)
    if athlete_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или устаревший CSRF state. Попробуйте подключить Strava снова."
        )

    # Обмен code → tokens
    token_data = await strava_oauth_service.exchange_code_for_tokens(code)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось получить токены от Strava API. Попробуйте позже."
        )

    # Шифруем токены и сохраняем в AthleteProfile
    encrypted = strava_oauth_service.extract_athlete_tokens(token_data)
    await db.execute(
        update(AthleteProfile)
        .where(AthleteProfile.id == athlete_id)
        .values(**encrypted)
    )
    await db.commit()

    strava_athlete_id = encrypted.get("strava_athlete_id")
    logger.info(f"Strava подключён: athlete_id={athlete_id}, strava_athlete_id={strava_athlete_id}")

    return {
        "status": "success",
        "message": "Strava успешно подключён. Ваши тренировки будут импортироваться автоматически.",
        "strava_athlete_id": strava_athlete_id,
    }


@router.delete("/disconnect", summary="Отключить Strava аккаунт")
async def strava_disconnect(
    athlete: AthleteProfile = Depends(get_current_athlete),
    db: AsyncSession = Depends(get_db),
):
    """
    Отзывает доступ к Strava и удаляет токены из БД.
    Реализует право на удаление данных (152-ФЗ, GDPR).
    """
    if not athlete.strava_access_token_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava аккаунт не подключён."
        )

    # Отзываем токен в Strava
    await strava_oauth_service.deauthorize(athlete.strava_access_token_encrypted)

    # Удаляем токены из БД
    await db.execute(
        update(AthleteProfile)
        .where(AthleteProfile.id == athlete.id)
        .values(
            strava_athlete_id=None,
            strava_access_token_encrypted=None,
            strava_refresh_token_encrypted=None,
            strava_token_expires_at=None,
            strava_scope=None,
        )
    )
    await db.commit()

    logger.info(f"Strava отключён: athlete_id={athlete.id}")
    return {"status": "success", "message": "Strava аккаунт отключён. Токены удалены."}


@router.get("/status", summary="Статус подключения Strava")
async def strava_status(
    athlete: AthleteProfile = Depends(get_current_athlete),
):
    """Возвращает текущий статус подключения Strava аккаунта."""
    connected = athlete.strava_athlete_id is not None
    return {
        "connected": connected,
        "strava_athlete_id": athlete.strava_athlete_id if connected else None,
        "scope": athlete.strava_scope if connected else None,
        "token_expires_at": athlete.strava_token_expires_at.isoformat() if athlete.strava_token_expires_at else None,
    }


# ─── Strava Webhook ──────────────────────────────────────────────────────────

@router.get("/webhook", summary="Верификация Strava webhook подписки")
async def strava_webhook_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
):
    """
    Верификационный challenge при регистрации Strava webhook подписки.
    Strava отправляет GET запрос для подтверждения владения URL.
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="hub.mode должен быть 'subscribe'")

    if hub_verify_token != settings.STRAVA_WEBHOOK_VERIFY_TOKEN:
        logger.warning(f"Strava webhook verify_token не совпадает: получен '{hub_verify_token}'")
        raise HTTPException(status_code=403, detail="Неверный verify_token")

    logger.info("Strava webhook subscription verified successfully")
    return {"hub.challenge": hub_challenge}


@router.post("/webhook", summary="Приём событий от Strava")
async def strava_webhook_receive(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Принимает push-события от Strava о новых/изменённых тренировках.

    event_type=create → delayed import через 1 час (даёт время на корректировки)
    event_type=update → обновление существующей записи в БД
    event_type=delete → помечаем активность как удалённую (soft delete)

    Аномальный ЧСС → запрос атлету о сбое датчика, а не немедленный Red Flag.
    """
    body = await request.body()

    # Верификация HMAC-подписи
    signature = request.headers.get("X-Hub-Signature", "")
    if settings.STRAVA_CLIENT_SECRET and signature:
        if not strava_webhook_validator.verify_webhook_signature(
            payload_body=body,
            signature_header=signature,
            client_secret=settings.STRAVA_CLIENT_SECRET,
        ):
            logger.warning("Strava webhook: неверная HMAC подпись")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    import json
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    object_type = payload.get("object_type", "")
    event_type = payload.get("aspect_type", "")  # create / update / delete
    strava_activity_id = payload.get("object_id")
    owner_id = payload.get("owner_id")  # strava athlete_id

    logger.info(
        f"Strava webhook: object_type={object_type}, event_type={event_type}, "
        f"activity_id={strava_activity_id}, owner_id={owner_id}"
    )

    if object_type != "activity":
        return {"status": "ignored", "reason": "not an activity event"}

    if strava_activity_id is None:
        return {"status": "ignored", "reason": "no object_id"}

    # Находим атлета по strava_athlete_id
    if owner_id:
        athlete_res = await db.execute(
            select(AthleteProfile).where(AthleteProfile.strava_athlete_id == owner_id)
        )
        athlete = athlete_res.scalar_one_or_none()
    else:
        athlete = None

    if athlete is None:
        logger.info(f"Strava webhook: атлет с strava_athlete_id={owner_id} не найден (не зарегистрирован)")
        return {"status": "ignored", "reason": "athlete not found"}

    if event_type == "create":
        # Delayed import — через 1 час после окончания тренировки
        # Это даёт время Strava обработать все корректировки (GPS, высота, дистанция)
        await _schedule_delayed_strava_fetch(
            athlete=athlete,
            strava_activity_id=strava_activity_id,
            db=db,
        )
        return {
            "status": "scheduled",
            "strava_activity_id": strava_activity_id,
            "fetch_delay_seconds": settings.STRAVA_FETCH_DELAY_SECONDS,
            "message": f"Импорт запланирован через {settings.STRAVA_FETCH_DELAY_SECONDS // 60} минут"
        }

    elif event_type == "update":
        # Обновление существующей тренировки (добавили описание, изменили тип и т.д.)
        await _update_strava_activity(
            athlete=athlete,
            strava_activity_id=strava_activity_id,
            updates=payload.get("updates", {}),
            db=db,
        )
        return {"status": "updated", "strava_activity_id": strava_activity_id}

    elif event_type == "delete":
        logger.info(f"Strava webhook: удаление активности {strava_activity_id} (не удаляем из нашей БД)")
        return {"status": "ignored", "reason": "delete events not processed"}

    return {"status": "ok"}


async def _schedule_delayed_strava_fetch(
    athlete: AthleteProfile,
    strava_activity_id: int,
    db: AsyncSession,
):
    """Планирует отложенный (1 час) импорт тренировки из Strava."""

    async def do_fetch():
        """Корутина, которую выполнит планировщик через 1 час."""
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await _import_strava_activity(
                athlete=athlete,
                strava_activity_id=strava_activity_id,
                db=session,
            )

    notification_scheduler.schedule_strava_fetch(
        fetch_coroutine_factory=do_fetch,
        delay_seconds=settings.STRAVA_FETCH_DELAY_SECONDS,
    )
    logger.info(
        f"Запланирован отложенный импорт: strava_activity_id={strava_activity_id}, "
        f"delay={settings.STRAVA_FETCH_DELAY_SECONDS}s"
    )


async def _import_strava_activity(
    athlete: AthleteProfile,
    strava_activity_id: int,
    db: AsyncSession,
):
    """
    Фактический импорт тренировки из Strava API:
    1. Загружаем данные из API
    2. Нормализуем в формат Activity
    3. Проверяем на дубликат
    4. Сохраняем в БД
    5. При аномальном ЧСС — запрашиваем атлета о сбое датчика
    6. Отправляем уведомление об успехе
    """
    # Загружаем данные из Strava API
    strava_data = await strava_activity_fetcher.fetch_activity(
        strava_activity_id=strava_activity_id,
        access_token_encrypted=athlete.strava_access_token_encrypted,
        refresh_token_encrypted=athlete.strava_refresh_token_encrypted,
        token_expires_at=athlete.strava_token_expires_at,
    )

    if strava_data is None:
        logger.error(f"Не удалось загрузить activity {strava_activity_id} из Strava")
        return

    # Нормализуем
    normalized = strava_normalizer.normalize(
        strava_data=strava_data,
        athlete_id=athlete.id,
        athlete_max_hr=athlete.max_hr,
    )

    hr_anomaly = normalized.pop("_hr_anomaly", False)
    max_hr_value = normalized.pop("_max_hr_value", None)

    # Проверка дубликата (UniqueConstraint: athlete_id + strava_activity_id)
    existing = await db.execute(
        select(Activity).where(
            Activity.athlete_id == athlete.id,
            Activity.strava_activity_id == strava_activity_id,
        )
    )
    existing_activity = existing.scalar_one_or_none()

    if existing_activity:
        # Обновляем существующую запись (тренировка уже была импортирована ранее)
        await db.execute(
            update(Activity)
            .where(Activity.id == existing_activity.id)
            .values(
                title=normalized["title"],
                duration_seconds=normalized["duration_seconds"],
                distance_meters=normalized.get("distance_meters"),
                avg_hr=normalized.get("avg_hr"),
                max_hr=normalized.get("max_hr"),
                total_elevation_gain=normalized.get("total_elevation_gain"),
                strava_fetched_at=normalized["strava_fetched_at"],
            )
        )
        await db.commit()
        logger.info(f"Strava activity {strava_activity_id} обновлена в БД")
        return

    # Создаём новую запись
    activity = Activity(**normalized)
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    logger.info(
        f"Strava activity импортирована: id={activity.id}, "
        f"title='{activity.title}', athlete_id={athlete.id}"
    )

    # Получаем chat_id атлета для уведомлений
    chat_id = None
    if athlete.telegram_chat_id_encrypted:
        chat_id = notification_service.decrypt_chat_id(athlete.telegram_chat_id_encrypted)

    # Аномальный ЧСС → спрашиваем о датчике, не триажируем автоматически
    if hr_anomaly and max_hr_value and chat_id:
        logger.warning(
            f"Аномальный ЧСС {max_hr_value} bpm в Strava activity {strava_activity_id} "
            f"— отправляем запрос о датчике атлету (athlete_id={athlete.id})"
        )
        await notification_service.send_strava_hr_sensor_check(
            chat_id=chat_id,
            activity_title=activity.title,
            max_hr=max_hr_value,
            strava_activity_id=strava_activity_id,
        )
    elif chat_id:
        # Обычное уведомление об успешном импорте
        dist_km = activity.distance_meters / 1000 if activity.distance_meters else None
        dur_min = (activity.duration_seconds or 0) // 60
        await notification_service.send_strava_import_done(
            chat_id=chat_id,
            activity_title=activity.title,
            duration_min=dur_min,
            distance_km=dist_km,
        )


async def _update_strava_activity(
    athlete: AthleteProfile,
    strava_activity_id: int,
    updates: dict,
    db: AsyncSession,
):
    """
    Обрабатывает event_type=update от Strava.
    Если тренировка уже в нашей БД — перезагружаем полные данные.
    Если нет — планируем delayed import (могли пропустить create event).
    """
    existing = await db.execute(
        select(Activity).where(
            Activity.athlete_id == athlete.id,
            Activity.strava_activity_id == strava_activity_id,
        )
    )
    existing_activity = existing.scalar_one_or_none()

    if existing_activity:
        # Обновляем название если изменилось
        if "title" in updates:
            await db.execute(
                update(Activity)
                .where(Activity.id == existing_activity.id)
                .values(title=updates["title"])
            )
            await db.commit()
            logger.info(f"Strava activity {strava_activity_id}: обновлено название → '{updates['title']}'")
    else:
        # Тренировки нет в БД — планируем импорт (с минимальной задержкой 30 сек)
        await _schedule_delayed_strava_fetch(athlete=athlete, strava_activity_id=strava_activity_id, db=db)
