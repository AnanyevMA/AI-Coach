from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AthleteProfile
from app.models.telemetry import HRVData, TelemetryRecord
from app.models.workout import WorkoutPlan, WorkoutSession, RedFlagLog


@dataclass
class TriageResult:
    flag_triggered: bool
    level: Optional[str]  # LEVEL_1_EMERGENCY, LEVEL_2_MEDICAL, LEVEL_3_CAUTION, or None
    trigger_condition: Optional[str]
    action_taken: Optional[str]
    lock_schedule: bool
    recommended_action: str


class RedFlagService:
    """
    Automated Red Flag Triage Engine for AI Adaptive Coach v7.0.
    Evaluates athlete physiological metrics against sports medicine safety protocols.
    """

    LEVEL_1_EMERGENCY = "LEVEL_1_EMERGENCY"
    LEVEL_2_MEDICAL = "LEVEL_2_MEDICAL"
    LEVEL_3_CAUTION = "LEVEL_3_CAUTION"

    # Emergency symptom keywords (Russian & English)
    EMERGENCY_SYMPTOMS = [
        "chest pain", "боль в груди", "fainting", "обморок", "dizziness", "головокружение",
        "dyspnea", "одышка", "palpitations", "сильное сердцебиение", "nausea", "тошнота"
    ]

    async def evaluate_athlete_status(
        self,
        db: AsyncSession,
        athlete_id: int,
        workout_session_id: Optional[int] = None,
        current_hr: Optional[int] = None,
        rpe_score: Optional[int] = None,
        symptoms_text: Optional[str] = None,
        latest_rmssd: Optional[float] = None,
        baseline_rmssd: Optional[float] = 50.0,
    ) -> TriageResult:
        """
        Main entry point for evaluating athlete telemetry and logging red flags.
        """
        # Fetch athlete profile for max_hr
        result = await db.execute(
            select(AthleteProfile).where(AthleteProfile.id == athlete_id)
        )
        athlete = result.scalar_one_or_none()
        max_hr = athlete.max_hr if athlete and athlete.max_hr else 190

        # Check Level 1 Emergency Lock
        is_l1, l1_cond, l1_action = self._check_level_1_emergency(
            current_hr=current_hr,
            max_hr=max_hr,
            symptoms_text=symptoms_text
        )
        if is_l1:
            triage = TriageResult(
                flag_triggered=True,
                level=self.LEVEL_1_EMERGENCY,
                trigger_condition=l1_cond,
                action_taken=l1_action,
                lock_schedule=True,
                recommended_action="Emergency Lock Activated. Stop activity immediately and seek medical attention."
            )
            await self._log_red_flag_and_lock(db, athlete_id, workout_session_id, triage)
            return triage

        # Fetch baseline HRV if not provided
        if latest_rmssd is None:
            hrv_res = await db.execute(
                select(HRVData)
                .where(HRVData.athlete_id == athlete_id)
                .order_by(HRVData.measured_at.desc())
                .limit(1)
            )
            latest_hrv = hrv_res.scalar_one_or_none()
            if latest_hrv:
                latest_rmssd = latest_hrv.rmssd

        # Check Level 2 Medical Lock
        is_l2, l2_cond, l2_action = self._check_level_2_medical(
            rpe_score=rpe_score,
            symptoms_text=symptoms_text,
            latest_rmssd=latest_rmssd,
            baseline_rmssd=baseline_rmssd
        )
        if is_l2:
            triage = TriageResult(
                flag_triggered=True,
                level=self.LEVEL_2_MEDICAL,
                trigger_condition=l2_cond,
                action_taken=l2_action,
                lock_schedule=True,
                recommended_action="Medical Lock Activated. High-intensity training suspended pending medical/coach review."
            )
            await self._log_red_flag_and_lock(db, athlete_id, workout_session_id, triage)
            return triage

        # Check Level 3 Caution Reset
        is_l3, l3_cond, l3_action = self._check_level_3_caution(
            rpe_score=rpe_score,
            latest_rmssd=latest_rmssd,
            baseline_rmssd=baseline_rmssd
        )
        if is_l3:
            triage = TriageResult(
                flag_triggered=True,
                level=self.LEVEL_3_CAUTION,
                trigger_condition=l3_cond,
                action_taken=l3_action,
                lock_schedule=False,
                recommended_action="Caution Reset Activated. Load reduced to active recovery for optimal adaptation."
            )
            await self._log_red_flag_and_lock(db, athlete_id, workout_session_id, triage)
            return triage

        return TriageResult(
            flag_triggered=False,
            level=None,
            trigger_condition=None,
            action_taken=None,
            lock_schedule=False,
            recommended_action="Status nominal. Proceed with regular training plan."
        )

    def _check_level_1_emergency(
        self,
        current_hr: Optional[int],
        max_hr: int,
        symptoms_text: Optional[str]
    ) -> Tuple[bool, str, str]:
        if symptoms_text:
            s_lower = symptoms_text.lower()
            for kw in self.EMERGENCY_SYMPTOMS:
                if kw in s_lower:
                    return (
                        True,
                        f"Critical acute symptom reported: '{kw}'",
                        "LEVEL 1 EMERGENCY LOCK: Immediate workout stop & emergency notification."
                    )

        if current_hr is not None:
            if current_hr >= 210:
                return (
                    True,
                    f"Extreme HR detected: {current_hr} bpm >= 210 bpm",
                    "LEVEL 1 EMERGENCY LOCK: Tachycardia emergency alert."
                )
            if current_hr > (max_hr + 15):
                return (
                    True,
                    f"Severe HR overload: {current_hr} bpm exceeds max_hr ({max_hr}) + 15 bpm",
                    "LEVEL 1 EMERGENCY LOCK: Immediate workout termination."
                )

        return (False, "", "")

    def _check_level_2_medical(
        self,
        rpe_score: Optional[int],
        symptoms_text: Optional[str],
        latest_rmssd: Optional[float],
        baseline_rmssd: Optional[float]
    ) -> Tuple[bool, str, str]:
        if rpe_score is not None and rpe_score >= 10:
            return (
                True,
                "Maximum exhaustion RPE=10 reported with joint/muscle strain",
                "LEVEL 2 MEDICAL LOCK: Suspension of high-intensity training plans."
            )

        if latest_rmssd is not None and baseline_rmssd and baseline_rmssd > 0:
            drop_pct = (baseline_rmssd - latest_rmssd) / baseline_rmssd * 100.0
            if drop_pct >= 35.0:
                return (
                    True,
                    f"Severe autonomic nervous system depression: HRV rMSSD dropped by {drop_pct:.1f}%",
                    "LEVEL 2 MEDICAL LOCK: Medical clearance required prior to heavy loads."
                )

        return (False, "", "")

    def _check_level_3_caution(
        self,
        rpe_score: Optional[int],
        latest_rmssd: Optional[float],
        baseline_rmssd: Optional[float]
    ) -> Tuple[bool, str, str]:
        if rpe_score is not None and rpe_score >= 8:
            return (
                True,
                f"Elevated effort RPE={rpe_score} during routine workout session",
                "LEVEL 3 CAUTION RESET: Target HR zone lowered to Active Recovery."
            )

        if latest_rmssd is not None and baseline_rmssd and baseline_rmssd > 0:
            drop_pct = (baseline_rmssd - latest_rmssd) / baseline_rmssd * 100.0
            if 15.0 <= drop_pct < 35.0:
                return (
                    True,
                    f"Moderate recovery deficit: HRV rMSSD dropped by {drop_pct:.1f}%",
                    "LEVEL 3 CAUTION RESET: Training volume scaled back by 30%."
                )

        return (False, "", "")

    async def _log_red_flag_and_lock(
        self,
        db: AsyncSession,
        athlete_id: int,
        workout_session_id: Optional[int],
        triage: TriageResult
    ) -> RedFlagLog:
        # Create DB log entry
        log_entry = RedFlagLog(
            athlete_id=athlete_id,
            workout_session_id=workout_session_id,
            level=triage.level or "UNKNOWN",
            trigger_condition=triage.trigger_condition or "",
            action_taken=triage.action_taken or "",
            resolved=False
        )
        db.add(log_entry)

        # Lock or modify active upcoming workout plans if necessary
        if triage.lock_schedule:
            await db.execute(
                update(WorkoutPlan)
                .where(
                    WorkoutPlan.athlete_id == athlete_id,
                    WorkoutPlan.status == "planned"
                )
                .values(status=f"locked_{triage.level.lower()}")
            )
        elif triage.level == self.LEVEL_3_CAUTION:
            await db.execute(
                update(WorkoutPlan)
                .where(
                    WorkoutPlan.athlete_id == athlete_id,
                    WorkoutPlan.status == "planned"
                )
                .values(status="modified", target_hr_zone="Zone 1-2 Recovery")
            )

        await db.commit()
        await db.refresh(log_entry)

        # ── Push-уведомление атлету при Red Flag Level 1 / 2 ────────────
        # Отправляем синхронно внутри триажа (P1 Medical: not async, not deferred)
        if triage.level in (self.LEVEL_1_EMERGENCY, self.LEVEL_2_MEDICAL):
            await self._send_red_flag_notification(db, athlete_id, triage)

        return log_entry

    async def _send_red_flag_notification(
        self,
        db: AsyncSession,
        athlete_id: int,
        triage: TriageResult,
    ):
        """
        Отправляет Telegram уведомление атлету при срабатывании Level 1 / 2.
        Импортируем notification_service внутри метода (избегаем circular import).
        """
        import logging
        _logger = logging.getLogger("red_flag_service")
        try:
            from app.services.notification_service import notification_service

            # Получаем AthleteProfile для получения chat_id
            athlete_res = await db.execute(
                select(AthleteProfile).where(AthleteProfile.id == athlete_id)
            )
            athlete = athlete_res.scalar_one_or_none()
            if not athlete:
                return

            # Проверяем opt-in на Red Flag уведомления
            if not athlete.notify_red_flag:
                return

            if not athlete.telegram_chat_id_encrypted:
                _logger.debug(f"Red Flag: атлет {athlete_id} не привязал Telegram")
                return

            chat_id = notification_service.decrypt_chat_id(athlete.telegram_chat_id_encrypted)
            if chat_id is None:
                return

            await notification_service.send_red_flag_alert(
                chat_id=chat_id,
                level=triage.level or "",
                trigger_condition=triage.trigger_condition or "",
                is_athlete=True,
            )
            _logger.info(f"Red Flag уведомление отправлено: athlete_id={athlete_id}, level={triage.level}")
        except Exception as exc:
            import logging
            logging.getLogger("red_flag_service").error(
                f"Red Flag notification error: {exc}", exc_info=True
            )


red_flag_service = RedFlagService()
