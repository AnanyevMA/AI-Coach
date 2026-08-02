"""
notification_scheduler.py — APScheduler-планировщик push-уведомлений.
AI Adaptive Coach v7.1

Стратегия: cron-задача каждую минуту проверяет, у каких атлетов
сейчас наступило персональное время чек-ина (UTC hour:minute).
Это позволяет у каждого атлета своё время без пересоздания джобов.

Дополнительно:
- Еженедельный дайджест (воскресенье 18:00 UTC)
- Одноразовые delayed-задачи для delayed Strava import (1 час)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_sensitive_data
from app.models.user import AthleteProfile, User
from app.services.notification_service import notification_service

logger = logging.getLogger("notification_scheduler")


class NotificationScheduler:
    """
    Планировщик push-уведомлений на базе APScheduler (asyncio).
    Запускается при старте FastAPI приложения.
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._db_factory = None  # AsyncSession factory, инициализируется при start()

    def set_db_factory(self, db_factory):
        """Инжектим фабрику сессий БД (вызывается из lifespan)."""
        self._db_factory = db_factory

    def start(self):
        """Запуск планировщика. Вызывается в FastAPI lifespan startup."""
        # Проверка персональных чек-ин времён — каждую минуту
        self.scheduler.add_job(
            self._check_and_send_morning_checkins,
            trigger=CronTrigger(minute="*"),  # каждую минуту
            id="morning_checkin_sweep",
            replace_existing=True,
            name="Morning Check-in Sweep (per-athlete UTC time)",
        )

        # Еженедельный дайджест — воскресенье 18:00 UTC
        self.scheduler.add_job(
            self._send_weekly_summaries,
            trigger=CronTrigger(day_of_week="sun", hour=18, minute=0),
            id="weekly_summary",
            replace_existing=True,
            name="Weekly Summary (Sunday 18:00 UTC)",
        )

        self.scheduler.start()
        logger.info("NotificationScheduler started: morning_checkin_sweep + weekly_summary")

    def stop(self):
        """Остановка планировщика. Вызывается в FastAPI lifespan shutdown."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("NotificationScheduler stopped.")

    def schedule_strava_fetch(self, fetch_coroutine_factory, delay_seconds: int = 3600):
        """
        Планирует одноразовую отложенную загрузку тренировки из Strava.
        По умолчанию задержка 1 час (даёт время Strava на корректировки дистанции/высоты).
        fetch_coroutine_factory — callable, возвращающий корутину для выполнения.
        """
        from datetime import timedelta
        run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        job_id = f"strava_fetch_{run_at.timestamp()}"
        self.scheduler.add_job(
            fetch_coroutine_factory,
            trigger="date",
            run_date=run_at,
            id=job_id,
            replace_existing=True,
            name=f"Delayed Strava Activity Fetch (in {delay_seconds}s)",
        )
        logger.info(f"Strava delayed fetch scheduled at {run_at.isoformat()} (job_id={job_id})")
        return job_id

    async def _check_and_send_morning_checkins(self):
        """
        Каждую минуту: проверяем всех атлетов, у кого сейчас наступило
        персональное время чек-ина (UTC hour:minute).
        """
        if self._db_factory is None:
            return

        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        current_minute = now_utc.minute

        try:
            async with self._db_factory() as db:
                result = await db.execute(
                    select(AthleteProfile).where(
                        AthleteProfile.notify_morning_checkin == True,
                        AthleteProfile.telegram_chat_id_encrypted.isnot(None),
                        AthleteProfile.notification_checkin_hour_utc == current_hour,
                        AthleteProfile.notification_checkin_minute_utc == current_minute,
                    )
                )
                athletes = result.scalars().all()

                if not athletes:
                    return

                logger.info(f"Morning checkin sweep: {len(athletes)} athlete(s) at {current_hour:02d}:{current_minute:02d} UTC")

                for athlete in athletes:
                    chat_id = notification_service.decrypt_chat_id(
                        athlete.telegram_chat_id_encrypted
                    )
                    if chat_id is None:
                        continue

                    # Получаем имя пользователя
                    user_res = await db.execute(
                        select(User).where(User.id == athlete.user_id)
                    )
                    user = user_res.scalar_one_or_none()
                    athlete_name = "атлет"
                    if user and user.full_name_encrypted:
                        try:
                            athlete_name = decrypt_sensitive_data(user.full_name_encrypted).split()[0]
                        except Exception:
                            pass

                    await notification_service.send_morning_checkin(
                        chat_id=chat_id,
                        athlete_name=athlete_name,
                    )
        except Exception as exc:
            logger.error(f"Ошибка в morning checkin sweep: {exc}", exc_info=True)

    async def _send_weekly_summaries(self):
        """
        Еженедельный дайджест — воскресенье 18:00 UTC.
        Отправляется всем атлетам с активной подпиской.
        """
        if self._db_factory is None:
            return

        try:
            async with self._db_factory() as db:
                result = await db.execute(
                    select(AthleteProfile).where(
                        AthleteProfile.notify_weekly_summary == True,
                        AthleteProfile.telegram_chat_id_encrypted.isnot(None),
                    )
                )
                athletes = result.scalars().all()
                logger.info(f"Weekly summary: отправка {len(athletes)} атлетам")

                for athlete in athletes:
                    chat_id = notification_service.decrypt_chat_id(
                        athlete.telegram_chat_id_encrypted
                    )
                    if chat_id is None:
                        continue

                    user_res = await db.execute(
                        select(User).where(User.id == athlete.user_id)
                    )
                    user = user_res.scalar_one_or_none()
                    athlete_name = "атлет"
                    if user and user.full_name_encrypted:
                        try:
                            athlete_name = decrypt_sensitive_data(user.full_name_encrypted).split()[0]
                        except Exception:
                            pass

                    await notification_service.send_weekly_summary(
                        chat_id=chat_id,
                        athlete_name=athlete_name,
                        # TODO: в следующей итерации — реальные данные из БД за неделю
                        workouts_count=0,
                        acwr=None,
                        hrv_trend=None,
                    )
        except Exception as exc:
            logger.error(f"Ошибка в weekly summary: {exc}", exc_info=True)


# Глобальный синглтон планировщика
notification_scheduler = NotificationScheduler()
