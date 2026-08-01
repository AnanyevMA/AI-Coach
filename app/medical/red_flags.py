from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TriageLevel(str, Enum):
    LEVEL_0_CLEAR = "LEVEL_0_CLEAR"
    LEVEL_1_EMERGENCY = "LEVEL_1_EMERGENCY"
    LEVEL_2_MEDICAL_REFERRAL = "LEVEL_2_MEDICAL_REFERRAL"
    LEVEL_3_CAUTION = "LEVEL_3_CAUTION"


class SystemAction(str, Enum):
    PROCEED = "PROCEED"
    HARD_LOCK = "HARD_LOCK"
    FREEZE_PLAN = "FREEZE_PLAN"
    REDUCE_LOAD = "REDUCE_LOAD"


@dataclass
class TriageAssessmentInput:
    # Level 1 Emergency Indicators
    chest_pain_or_pressure: bool = False
    syncope_or_dizziness: bool = False
    palpitations_at_rest: bool = False
    dark_urine_rhabdo_suspect: bool = False

    # Level 2 Medical Lock Indicators
    fever_celsius: float = 36.6
    inability_to_bear_weight: bool = False  # Ottawa rules
    knee_pain_vas: int = 0                  # Visual Analog Scale 0-10
    hrv_z_score: float = 0.0                # Heart Rate Variability z-score
    acwr: float = 1.0                       # Acute:Chronic Workload Ratio

    # Level 3 Caution Reset Indicators
    rhr_elevation_bpm: int = 0              # Resting HR elevation above baseline


@dataclass
class TriageResult:
    triage_level: TriageLevel
    action: SystemAction
    message: str
    call_emergency: bool = False
    referral_specialist: Optional[str] = None
    volume_reduction: float = 0.0


class RedFlagsTriageEngine:
    """
    Medical Triage Engine for AI Adaptive Coach v7.0.
    Evaluates athlete telemetry and self-reported symptoms to enforce:
    - Level 1: Emergency Hard Lock (Chest pain, syncope, arrhythmia, rhabdomyolysis)
    - Level 2: Medical Referral Lock (Severe HRV drop z < -3.0, ACWR > 1.5, Fever >= 37.5°C, Ottawa trauma, VAS >= 6)
    - Level 3: Caution Adaptive Reset (Moderate HRV drop z < -1.5, RHR elevation >= 10, VAS 3-5, ACWR 1.3-1.5)
    """

    def evaluate(self, data: TriageAssessmentInput) -> TriageResult:
        # LEVEL 1: EMERGENCY HARD LOCK (Cardiovascular & Rhabdomyolysis Red Flags)
        if (
            data.chest_pain_or_pressure
            or data.syncope_or_dizziness
            or data.palpitations_at_rest
            or data.dark_urine_rhabdo_suspect
        ):
            triggers = []
            if data.chest_pain_or_pressure:
                triggers.append("боль/давление за грудиной")
            if data.syncope_or_dizziness:
                triggers.append("головокружение/прединкопе")
            if data.palpitations_at_rest:
                triggers.append("аритмия/пальпитации в покое")
            if data.dark_urine_rhabdo_suspect:
                triggers.append("подозрение на рабдомиолиз (темная моча)")

            return TriageResult(
                triage_level=TriageLevel.LEVEL_1_EMERGENCY,
                action=SystemAction.HARD_LOCK,
                message=(
                    f"🚨 КРИТИЧЕСКИЙ КРАСНЫЙ ФЛАГ ({', '.join(triggers)})! "
                    "Немедленно прекратите тренировку и вызовите скорую помощь (112)."
                ),
                call_emergency=True,
                referral_specialist="Кардиолог / Скорая Медицинская Помощь"
            )

        # LEVEL 2: MEDICAL REFERRAL LOCK (Severe HRV Drop, High ACWR, Fever, Structural Trauma)
        if (
            data.hrv_z_score < -3.0
            or data.acwr > 1.5
            or data.fever_celsius >= 37.5
            or data.inability_to_bear_weight
            or data.knee_pain_vas >= 6
        ):
            triggers = []
            if data.hrv_z_score < -3.0:
                triggers.append(f"критический срыв ВСР (z={data.hrv_z_score:.2f})")
            if data.acwr > 1.5:
                triggers.append(f"высокий ACWR ({data.acwr:.2f})")
            if data.fever_celsius >= 37.5:
                triggers.append(f"лихорадка ({data.fever_celsius}°C)")
            if data.inability_to_bear_weight:
                triggers.append("невозможность осевой нагрузки (Ottawa)")
            if data.knee_pain_vas >= 6:
                triggers.append(f"выраженная боль в колене (VAS {data.knee_pain_vas}/10)")

            return TriageResult(
                triage_level=TriageLevel.LEVEL_2_MEDICAL_REFERRAL,
                action=SystemAction.FREEZE_PLAN,
                message=(
                    f"⏸️ МЕДИЦИНСКАЯ БЛОКИРОВКА ({', '.join(triggers)}). "
                    "Тренировочный план заморожен. Требуется консультация врача."
                ),
                call_emergency=False,
                referral_specialist="Спортивный врач / Травматолог / Кардиолог"
            )

        # LEVEL 3: CAUTION ADAPTIVE RESET (Moderate HRV Drop, Elevated RHR, Moderate ACWR/VAS)
        if (
            data.hrv_z_score < -1.5
            or data.rhr_elevation_bpm >= 10
            or (1.3 <= data.acwr <= 1.5)
            or (3 <= data.knee_pain_vas <= 5)
        ):
            triggers = []
            if data.hrv_z_score < -1.5:
                triggers.append(f"спад ВСР (z={data.hrv_z_score:.2f})")
            if data.rhr_elevation_bpm >= 10:
                triggers.append(f"прирост ЧСС покоя (+{data.rhr_elevation_bpm} bpm)")
            if 1.3 <= data.acwr <= 1.5:
                triggers.append(f"повышенный ACWR ({data.acwr:.2f})")
            if 3 <= data.knee_pain_vas <= 5:
                triggers.append(f"умеренная боль в колене (VAS {data.knee_pain_vas}/10)")

            return TriageResult(
                triage_level=TriageLevel.LEVEL_3_CAUTION,
                action=SystemAction.REDUCE_LOAD,
                message=(
                    f"⚠️ ВНИМАНИЕ: СНИЖЕНИЕ НАГРУЗКИ ({', '.join(triggers)}). "
                    "Объем снижен на 50%, только восстановительная зона Z1."
                ),
                call_emergency=False,
                volume_reduction=0.50
            )

        # LEVEL 0: ALL CLEAR
        return TriageResult(
            triage_level=TriageLevel.LEVEL_0_CLEAR,
            action=SystemAction.PROCEED,
            message="🟢 Все показатели в норме. Готовность к тренировке высокая.",
            call_emergency=False
        )

    @staticmethod
    def evaluate_caution_reset(
        hrv_z_score: float,
        knee_pain_vas: int,
        hours_elapsed_in_rest: int
    ) -> bool:
        """
        Evaluates whether a Level 3 Caution status can be reset to Level 0.
        Requires HRV z-score > -1.0, knee VAS <= 2, and at least 48 hours of recovery.
        """
        if hours_elapsed_in_rest < 48:
            return False
        return (hrv_z_score > -1.0) and (knee_pain_vas <= 2)
