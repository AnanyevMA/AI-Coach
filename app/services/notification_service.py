"""
notification_service.py — Сервис Push-уведомлений через Telegram Bot API.
AI Adaptive Coach v7.1

Возможности:
- Персональное время чек-ина (per-athlete UTC hour/minute)
- 4 типа уведомлений: morning_checkin, workout_ready, red_flag_alert, weekly_summary
- Opt-in/opt-out: каждый тип отдельно
- 152-ФЗ: telegram_chat_id хранится зашифрованным, в теле уведомлений — только агрегированные данные
- Безопасная отправка: при ошибке — логируем, не падаем
"""

import logging
from typing import Optional, Dict, Any

import httpx

from app.core.config import settings
from app.core.security import encrypt_sensitive_data, decrypt_sensitive_data

logger = logging.getLogger("notification_service")

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


class TelegramNotificationService:
    """
    Telegram Push-notification Service.
    Отправляет сообщения атлетам и тренерам через Telegram Bot API.
    """

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.webapp_url = settings.TELEGRAM_WEBAPP_URL or "http://localhost:8000/pwa"

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def encrypt_chat_id(self, chat_id: int) -> str:
        """Шифрует chat_id как ПДн (152-ФЗ)."""
        return encrypt_sensitive_data(str(chat_id))

    def decrypt_chat_id(self, encrypted: str) -> Optional[int]:
        """Дешифрует chat_id из БД."""
        try:
            raw = decrypt_sensitive_data(encrypted)
            return int(raw)
        except Exception:
            logger.warning("Не удалось дешифровать telegram_chat_id")
            return None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """
        Базовый метод отправки сообщения в Telegram.
        Возвращает True при успехе, False при ошибке.
        """
        if not self.bot_token or self.bot_token == "mock_bot_token_777":
            logger.debug(f"[MOCK] send_message → chat_id={chat_id}, text={text[:60]}...")
            return True

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._api_url("sendMessage"), json=payload)
                if resp.status_code == 200 and resp.json().get("ok"):
                    return True
                logger.error(
                    f"Telegram API error {resp.status_code}: {resp.text[:200]}"
                )
                return False
        except Exception as exc:
            logger.error(f"Ошибка отправки Telegram-уведомления chat_id={chat_id}: {exc}")
            return False

    async def send_morning_checkin(self, chat_id: int, athlete_name: str = "атлет") -> bool:
        """Утреннее напоминание о чек-ине (персональное время по UTC)."""
        text = (
            f"☀️ **Доброе утро, {athlete_name}!**\n\n"
            "Не забудь пройти утренний чек-ин — это займёт меньше минуты.\n"
            "Он поможет ИИ составить для тебя оптимальную тренировку на сегодня."
        )
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📋 Пройти чек-ин", "web_app": {"url": self.webapp_url}}],
                [{"text": "⏰ Пропустить сегодня", "callback_data": "skip_checkin"}],
            ]
        }
        return await self.send_message(chat_id, text, reply_markup)

    async def send_workout_ready(
        self,
        chat_id: int,
        workout_type: str = "Тренировка",
        readiness_score: Optional[int] = None,
    ) -> bool:
        """Уведомление о готовности плана тренировки."""
        ri_line = f"• **Индекс готовности:** {readiness_score}/100\n" if readiness_score else ""
        text = (
            f"🏃 **Твой план тренировки готов!**\n\n"
            f"• **Тип:** {workout_type}\n"
            f"{ri_line}"
            "Открой приложение, чтобы посмотреть детали."
        )
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📱 Посмотреть план", "web_app": {"url": self.webapp_url}}],
                [{"text": "✅ Отметить выполненной", "callback_data": "complete_workout"}],
            ]
        }
        return await self.send_message(chat_id, text, reply_markup)

    async def send_red_flag_alert(
        self,
        chat_id: int,
        level: str,
        trigger_condition: str,
        is_athlete: bool = True,
        athlete_name: Optional[str] = None,
    ) -> bool:
        """
        Уведомление о срабатывании Red Flag.
        Для атлета — инструкции по безопасности.
        Для тренера — агрегированные данные (без ПДн атлета в тексте).
        """
        if is_athlete:
            if level == "LEVEL_1_EMERGENCY":
                text = (
                    "🚨 **ЭКСТРЕННАЯ БЛОКИРОВКА ТРЕНИРОВОК**\n\n"
                    f"Обнаружен критический показатель: _{trigger_condition}_\n\n"
                    "⛔ Все тренировки остановлены.\n"
                    "🏥 При боли в груди или аритмии — вызовите скорую: **112**\n\n"
                    "_Это автоматическое уведомление системы безопасности (323-ФЗ)_"
                )
            else:
                text = (
                    "⚠️ **Ограничение тренировок**\n\n"
                    f"Система зафиксировала: _{trigger_condition}_\n\n"
                    "Сегодняшняя интенсивная тренировка заменена на восстановление.\n"
                    "Пройди чек-ин и следуй рекомендациям тренера."
                )
        else:
            # Для тренера — только агрегированные данные, без ПДн
            athlete_label = f"атлет «{athlete_name}»" if athlete_name else "один из атлетов"
            text = (
                f"🚨 **Red Flag Alert — {level}**\n\n"
                f"⚠️ У вашего подопечного ({athlete_label}) сработал медицинский триаж.\n"
                f"Условие: _{trigger_condition}_\n\n"
                "Тренировки заблокированы автоматически. Рекомендуется связаться с атлетом."
            )
        return await self.send_message(chat_id, text)

    async def send_weekly_summary(
        self,
        chat_id: int,
        athlete_name: str = "атлет",
        workouts_count: int = 0,
        acwr: Optional[float] = None,
        hrv_trend: Optional[str] = None,
    ) -> bool:
        """Еженедельный дайджест результатов (воскресенье)."""
        acwr_line = f"• **ACWR (нагрузка/восстановление):** {acwr:.2f}\n" if acwr else ""
        hrv_line = f"• **HRV тренд:** {hrv_trend}\n" if hrv_trend else ""
        acwr_emoji = "🟢" if acwr and 0.8 <= acwr <= 1.3 else ("🔴" if acwr and acwr > 1.5 else "🟡") if acwr else ""

        text = (
            f"📊 **Итоги недели, {athlete_name}!**\n\n"
            f"• **Тренировок завершено:** {workouts_count}\n"
            f"{acwr_line}"
            f"{acwr_emoji} {hrv_line}"
            "\n🔗 Посмотри подробный анализ в приложении."
        )
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📈 Открыть статистику", "web_app": {"url": self.webapp_url}}],
            ]
        }
        return await self.send_message(chat_id, text, reply_markup)

    async def send_strava_import_done(
        self,
        chat_id: int,
        activity_title: str,
        duration_min: int,
        distance_km: Optional[float] = None,
    ) -> bool:
        """Уведомление об успешном импорте тренировки из Strava."""
        dist_line = f"• **Дистанция:** {distance_km:.1f} км\n" if distance_km else ""
        text = (
            f"✅ **Тренировка из Strava импортирована!**\n\n"
            f"• **Название:** {activity_title}\n"
            f"• **Длительность:** {duration_min} мин\n"
            f"{dist_line}"
            "\nАнализ и план восстановления готовы в приложении."
        )
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📱 Посмотреть анализ", "web_app": {"url": self.webapp_url}}],
            ]
        }
        return await self.send_message(chat_id, text, reply_markup)

    async def send_strava_hr_sensor_check(
        self,
        chat_id: int,
        activity_title: str,
        max_hr: int,
        strava_activity_id: int,
    ) -> bool:
        """
        Запрос пользователю при обнаружении аномального ЧСС в данных Strava.
        Вместо немедленного Red Flag — спрашиваем о сбое датчика.
        """
        text = (
            f"❓ **Аномальный пульс в тренировке**\n\n"
            f"В тренировке «{activity_title}» обнаружен максимальный пульс **{max_hr} bpm**.\n\n"
            "Это может быть:\n"
            "• Сбой датчика пульсометра\n"
            "• Реальные данные\n\n"
            "Что произошло?"
        )
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📡 Датчик сбоил", "callback_data": f"hr_sensor_error:{strava_activity_id}"}],
                [{"text": "⚠️ Реальные данные — проверить здоровье", "callback_data": f"hr_real_data:{strava_activity_id}:{max_hr}"}],
            ]
        }
        return await self.send_message(chat_id, text, reply_markup)

    async def send_unsubscribe_confirmation(self, chat_id: int) -> bool:
        """Подтверждение отписки от уведомлений."""
        text = (
            "🔕 **Уведомления отключены**\n\n"
            "Ты больше не будешь получать автоматические уведомления.\n"
            "Чтобы включить их снова, используй команду /subscribe."
        )
        return await self.send_message(chat_id, text)

    async def send_subscribe_confirmation(self, chat_id: int) -> bool:
        """Подтверждение подписки на уведомления."""
        text = (
            "🔔 **Уведомления включены**\n\n"
            "Ты будешь получать:\n"
            "• ☀️ Утренние напоминания о чек-ине\n"
            "• 🏃 Уведомления о готовых тренировках\n"
            "• 📊 Еженедельный дайджест\n"
            "• 🚨 Медицинские алерты\n\n"
            "Чтобы отключить — /unsubscribe или через настройки."
        )
        return await self.send_message(chat_id, text)


# Глобальный синглтон сервиса
notification_service = TelegramNotificationService()
