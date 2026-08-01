"""
Pytest suite for Offline Fallback Adaptation Engine.
Tests offline workout adaptation when Z_HRV < -1.5, ACWR > 1.4, high DOMS,
or missing telemetry data.
Part of Phase 2 Test Suite for AI Adaptive Coach v7.0.
"""

import pytest

from app.services.fallback_engine import (
    OfflineFallbackEngine,
    FallbackInput,
    FallbackWorkoutPlan,
    FallbackActivityType,
    offline_fallback_engine
)


class TestOfflineFallbackEngine:
    """Test suite for offline heuristic adaptation rules in AI Adaptive Coach v7.0."""

    @pytest.fixture
    def engine(self) -> OfflineFallbackEngine:
        return offline_fallback_engine

    # =========================================================================
    # 1. HRV DROP ADAPTATION TESTS (Z_HRV < -1.5)
    # =========================================================================
    def test_fallback_adaptation_low_hrv_z_score(self, engine: OfflineFallbackEngine):
        """Verify Z_HRV < -1.5 reduces volume by 50% and caps intensity to Z1_RECOVERY."""
        data = FallbackInput(
            scheduled_activity_type="MODIFIED_RUNNING",
            original_duration_minutes=60,
            original_target_zone="Z3_TEMPO",
            hrv_z_score=-1.8,
            acwr=1.1,
            doms_score=2,
            is_wearable_synced=True
        )

        plan = engine.adapt_workout(data)

        assert plan.adapted_duration_minutes == 30  # 60 * 0.50
        assert plan.adapted_target_zone == "Z1_RECOVERY"
        assert plan.intensity_capped is True
        assert plan.volume_reduction_percentage == 50.0
        assert any("спад ВСР" in reason or "снижение ВСР" in reason for reason in plan.adaptation_reasons)

    # =========================================================================
    # 2. ACWR HIGH WORKLOAD ADAPTATION TESTS (ACWR > 1.4)
    # =========================================================================
    def test_fallback_adaptation_high_acwr(self, engine: OfflineFallbackEngine):
        """Verify ACWR > 1.4 reduces volume by 40% and caps intensity to prevent overtraining."""
        data = FallbackInput(
            scheduled_activity_type="MODIFIED_RUNNING",
            original_duration_minutes=60,
            original_target_zone="Z4_THRESHOLD",
            hrv_z_score=0.1,
            acwr=1.52,
            doms_score=2,
            is_wearable_synced=True
        )

        plan = engine.adapt_workout(data)

        assert plan.adapted_duration_minutes == 36  # 60 * 0.60
        assert plan.adapted_target_zone == "Z1_RECOVERY"
        assert plan.intensity_capped is True
        assert plan.volume_reduction_percentage == 40.0
        assert any("ACWR" in reason for reason in plan.adaptation_reasons)

    # =========================================================================
    # 3. HIGH DOMS ADAPTATION TESTS (DOMS >= 6/10)
    # =========================================================================
    def test_fallback_adaptation_high_doms_switches_activity(self, engine: OfflineFallbackEngine):
        """Verify high DOMS (>= 6/10) switches high-impact running to low-impact cycling."""
        data = FallbackInput(
            scheduled_activity_type="MODIFIED_RUNNING",
            original_duration_minutes=50,
            original_target_zone="Z3_TEMPO",
            hrv_z_score=-0.2,
            acwr=1.0,
            doms_score=7,  # Severe DOMS
            is_wearable_synced=True
        )

        plan = engine.adapt_workout(data)

        assert plan.adapted_activity_type == FallbackActivityType.LOW_IMPACT_CYCLING
        assert plan.adapted_target_zone == "Z1_RECOVERY"
        assert plan.intensity_capped is True
        assert any("DOMS" in reason for reason in plan.adaptation_reasons)

    # =========================================================================
    # 4. MISSING TELEMETRY (15% SAFETY FACTOR) TESTS
    # =========================================================================
    def test_fallback_adaptation_missing_telemetry_applies_safety_factor(self, engine: OfflineFallbackEngine):
        """Verify un-synced wearable applies 15% safety reduction factor (0.85)."""
        data = FallbackInput(
            scheduled_activity_type="LOW_IMPACT_CYCLING",
            original_duration_minutes=60,
            original_target_zone="Z2_ENDURANCE",
            hrv_z_score=0.0,
            acwr=1.0,
            doms_score=1,
            is_wearable_synced=False  # No telemetry data
        )

        plan = engine.adapt_workout(data)

        assert plan.applied_safety_factor == 0.85
        assert plan.adapted_duration_minutes == 51  # 60 * 0.85
        assert any("15% фактор безопасности" in reason for reason in plan.adaptation_reasons)

    # =========================================================================
    # 5. COMBINED RISK & NORMAL BASELINE TESTS
    # =========================================================================
    def test_fallback_adaptation_combined_risks(self, engine: OfflineFallbackEngine):
        """Verify combined Z_HRV < -1.5, ACWR > 1.4, and high DOMS apply compound safety constraints."""
        data = FallbackInput(
            scheduled_activity_type="MODIFIED_RUNNING",
            original_duration_minutes=60,
            original_target_zone="Z4_THRESHOLD",
            hrv_z_score=-2.0,
            acwr=1.45,
            doms_score=8,
            is_wearable_synced=True
        )

        plan = engine.adapt_workout(data)

        # Compound volume reduction: 0.50 (HRV) * 0.60 (ACWR) = 0.30 -> 18 min
        assert plan.adapted_duration_minutes == 18
        assert plan.adapted_target_zone == "Z1_RECOVERY"
        assert plan.adapted_activity_type == FallbackActivityType.LOW_IMPACT_CYCLING
        assert len(plan.adaptation_reasons) == 3

    def test_fallback_adaptation_normal_baseline(self, engine: OfflineFallbackEngine):
        """Verify healthy baseline metrics result in zero volume reduction."""
        data = FallbackInput(
            scheduled_activity_type="LOW_IMPACT_CYCLING",
            original_duration_minutes=60,
            original_target_zone="Z2_ENDURANCE",
            hrv_z_score=0.5,
            acwr=1.1,
            doms_score=1,
            is_wearable_synced=True
        )

        plan = engine.adapt_workout(data)

        assert plan.adapted_duration_minutes == 60
        assert plan.adapted_target_zone == "Z2_ENDURANCE"
        assert plan.volume_reduction_percentage == 0.0
        assert plan.intensity_capped is False
        assert len(plan.adaptation_reasons) == 0
