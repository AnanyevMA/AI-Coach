"""
Offline Fallback Engine for AI Adaptive Coach v7.0.
Provides deterministic, offline workout adaptation rules without API calls when network/LLM is unavailable
or when physiological caution thresholds (Z_HRV < -1.5, ACWR > 1.4, high DOMS/fatigue) are met.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class FallbackActivityType(str, Enum):
    ACTIVE_RECOVERY = "ACTIVE_RECOVERY"
    LOW_IMPACT_CYCLING = "LOW_IMPACT_CYCLING"
    SWIMMING = "SWIMMING"
    MOBILITY_AND_FOAM_ROLLING = "MOBILITY_AND_FOAM_ROLLING"
    MODIFIED_RUNNING = "MODIFIED_RUNNING"
    REST_DAY = "REST_DAY"


@dataclass
class FallbackInput:
    scheduled_activity_type: str = "RUNNING"
    original_duration_minutes: int = 60
    original_target_zone: str = "Z3_TEMPO"
    hrv_z_score: float = 0.0
    acwr: float = 1.0
    doms_score: int = 0                     # 0 - 10 DOMS scale
    knee_pain_vas: int = 0                  # 0 - 10 VAS pain scale
    rhr_elevation_bpm: int = 0
    fatigue_score: int = 0                  # Subjective fatigue score 0 - 10
    is_wearable_synced: bool = True         # Wearable telemetry availability


@dataclass
class FallbackWorkoutPlan:
    adapted_activity_type: FallbackActivityType
    adapted_duration_minutes: int
    adapted_target_zone: str
    volume_reduction_percentage: float
    intensity_capped: bool
    adaptation_reasons: List[str] = field(default_factory=list)
    applied_safety_factor: float = 1.0
    is_offline_fallback: bool = True
    coaching_notes: str = ""


class OfflineFallbackEngine:
    """
    Offline Heuristic Adaptation Engine.
    Executes deterministic sports medicine safety rules without LLM API calls.
    - Replaces high-intensity workouts (VO2max, Tempo, Threshold, Interval) with Zone 2 / Recovery when Z_HRV < -1.5 or ACWR > 1.4.
    - Auto-reduces volume by 30-50% for high fatigue / DOMS.
    """

    HIGH_INTENSITY_ZONES = {"Z3_TEMPO", "Z4_THRESHOLD", "Z5_VO2MAX", "Z6_ANAEROBIC", "VO2MAX", "TEMPO", "THRESHOLD", "INTERVALS"}

    def adapt_workout(self, data: FallbackInput) -> FallbackWorkoutPlan:
        reasons: List[str] = []
        volume_factor = 1.0
        capped_zone = data.original_target_zone

        activity_str = data.scheduled_activity_type
        if activity_str in FallbackActivityType.__members__:
            activity_type = FallbackActivityType(activity_str)
        else:
            activity_type = FallbackActivityType.MODIFIED_RUNNING

        intensity_capped = False

        # Rule 1: Missing Wearable Telemetry (15% safety factor on subjective metrics)
        safety_factor = 1.0
        if not data.is_wearable_synced:
            safety_factor = 0.85
            volume_factor *= safety_factor
            reasons.append("Телеметрия недоступна: применен 15% фактор безопасности к нагрузке")

        # Rule 2: Low HRV Z-Score (Z_HRV < -1.5) -> Replace high intensity with Z1/Z2 recovery & volume -50%
        if data.hrv_z_score < -1.5:
            volume_factor *= 0.50
            capped_zone = "Z1_RECOVERY"
            intensity_capped = True
            reasons.append(f"Выраженное снижение ВСР (z={data.hrv_z_score:.2f}): спад ВСР, объем -50%, замена интенсивности на восстановление")

        # Rule 3: High ACWR (ACWR > 1.4) -> Replace high intensity with Z1/Z2 recovery & volume -40%
        if data.acwr > 1.4:
            volume_factor *= 0.60
            if capped_zone not in ["Z1_RECOVERY", "Z2_ENDURANCE"]:
                capped_zone = "Z1_RECOVERY"
            intensity_capped = True
            reasons.append(f"Высокий индекс ACWR ({data.acwr:.2f} > 1.4): риск перетренированности, замена интенсивности на восстановление, объем -40%")

        # Rule 4: High Fatigue / Severe DOMS (DOMS >= 6/10 or fatigue >= 6/10) -> Auto volume reduction 30-50% & switch high-impact running
        if data.doms_score >= 6 or data.fatigue_score >= 6:
            intensity_capped = True
            if capped_zone not in ["Z1_RECOVERY", "Z2_ENDURANCE"]:
                capped_zone = "Z1_RECOVERY"
            reasons.append(f"Высокая мышечная боль DOMS ({data.doms_score}/10): замена бега на низкоударную нагрузку")
            if activity_type in [FallbackActivityType.MODIFIED_RUNNING, FallbackActivityType.ACTIVE_RECOVERY]:
                activity_type = FallbackActivityType.LOW_IMPACT_CYCLING

        # Rule 5: Knee Pain (VAS 3-5)
        if 3 <= data.knee_pain_vas <= 5:
            volume_factor *= 0.50
            activity_type = FallbackActivityType.MOBILITY_AND_FOAM_ROLLING
            capped_zone = "Z1_RECOVERY"
            reasons.append(f"Умеренная боль в колене (VAS {data.knee_pain_vas}/10): переключение на миофасциальный релиз и мобильность")

        # Compute adapted parameters
        adapted_duration = max(15, int(round(data.original_duration_minutes * volume_factor)))
        total_vol_reduction = round((1.0 - volume_factor) * 100.0, 1)

        notes = " ".join(reasons) if reasons else "Оффлайн адаптация: показатели стабильны."

        return FallbackWorkoutPlan(
            adapted_activity_type=activity_type,
            adapted_duration_minutes=adapted_duration,
            adapted_target_zone=capped_zone,
            volume_reduction_percentage=max(0.0, total_vol_reduction),
            intensity_capped=intensity_capped,
            adaptation_reasons=reasons,
            applied_safety_factor=safety_factor,
            is_offline_fallback=True,
            coaching_notes=notes
        )


offline_fallback_engine = OfflineFallbackEngine()
