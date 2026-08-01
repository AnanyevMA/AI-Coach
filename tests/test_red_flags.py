import pytest
from app.medical.red_flags import (
    RedFlagsTriageEngine,
    TriageAssessmentInput,
    TriageLevel,
    SystemAction
)


class TestRedFlagsMedicalTriage:
    """Test suite for sports medicine red flag triage engine in AI Adaptive Coach v7.0."""

    @pytest.fixture
    def triage_engine(self) -> RedFlagsTriageEngine:
        return RedFlagsTriageEngine()

    # =========================================================================
    # LEVEL 1: EMERGENCY HARD LOCK TESTS
    # =========================================================================
    def test_level1_emergency_chest_pain(self, triage_engine: RedFlagsTriageEngine):
        """Verify chest pain/pressure triggers Level 1 Emergency Hard Lock immediately."""
        data = TriageAssessmentInput(chest_pain_or_pressure=True)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_1_EMERGENCY
        assert result.action == SystemAction.HARD_LOCK
        assert result.call_emergency is True
        assert "боль/давление за грудиной" in result.message

    def test_level1_emergency_arrhythmia_at_rest(self, triage_engine: RedFlagsTriageEngine):
        """Verify resting arrhythmia/palpitations trigger Level 1 Emergency Lock."""
        data = TriageAssessmentInput(palpitations_at_rest=True)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_1_EMERGENCY
        assert result.action == SystemAction.HARD_LOCK
        assert result.call_emergency is True
        assert "аритмия/пальпитации в покое" in result.message

    def test_level1_emergency_syncope(self, triage_engine: RedFlagsTriageEngine):
        """Verify syncope or severe dizziness during exercise triggers Level 1 Emergency Lock."""
        data = TriageAssessmentInput(syncope_or_dizziness=True)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_1_EMERGENCY
        assert result.action == SystemAction.HARD_LOCK
        assert result.call_emergency is True

    def test_level1_emergency_rhabdomyolysis(self, triage_engine: RedFlagsTriageEngine):
        """Verify suspect dark urine (rhabdomyolysis) triggers Level 1 Emergency Lock."""
        data = TriageAssessmentInput(dark_urine_rhabdo_suspect=True)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_1_EMERGENCY
        assert result.action == SystemAction.HARD_LOCK
        assert result.call_emergency is True
        assert "рабдомиолиз" in result.message

    # =========================================================================
    # LEVEL 2: MEDICAL REFERRAL LOCK TESTS
    # =========================================================================
    def test_level2_medical_lock_critical_hrv_drop(self, triage_engine: RedFlagsTriageEngine):
        """Verify severe HRV drop (z < -3.0) triggers Level 2 Medical Lock (Freeze Plan)."""
        data = TriageAssessmentInput(hrv_z_score=-3.2)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL
        assert result.action == SystemAction.FREEZE_PLAN
        assert result.call_emergency is False
        assert result.referral_specialist is not None

    def test_level2_medical_lock_high_acwr(self, triage_engine: RedFlagsTriageEngine):
        """Verify dangerous ACWR (> 1.5) triggers Level 2 Medical Lock."""
        data = TriageAssessmentInput(acwr=1.65)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL
        assert result.action == SystemAction.FREEZE_PLAN

    def test_level2_medical_lock_fever(self, triage_engine: RedFlagsTriageEngine):
        """Verify fever (>= 37.5°C) triggers Level 2 Medical Lock to prevent viral myocarditis."""
        data = TriageAssessmentInput(fever_celsius=38.1)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL
        assert result.action == SystemAction.FREEZE_PLAN
        assert "лихорадка" in result.message

    def test_level2_medical_lock_ottawa_rules(self, triage_engine: RedFlagsTriageEngine):
        """Verify Ottawa ankle/foot rule (inability to bear weight) triggers Level 2 Medical Lock."""
        data = TriageAssessmentInput(inability_to_bear_weight=True)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL
        assert result.action == SystemAction.FREEZE_PLAN

    def test_level2_medical_lock_severe_knee_pain(self, triage_engine: RedFlagsTriageEngine):
        """Verify acute knee pain VAS >= 6 triggers Level 2 Medical Lock."""
        data = TriageAssessmentInput(knee_pain_vas=7)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL
        assert result.action == SystemAction.FREEZE_PLAN

    # =========================================================================
    # LEVEL 3: CAUTION ADAPTIVE RESET TESTS
    # =========================================================================
    def test_level3_caution_moderate_hrv_drop(self, triage_engine: RedFlagsTriageEngine):
        """Verify moderate HRV drop (z = -2.0) triggers Level 3 Caution Adaptive Reset (50% load reduction)."""
        data = TriageAssessmentInput(hrv_z_score=-2.0)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_3_CAUTION
        assert result.action == SystemAction.REDUCE_LOAD
        assert result.volume_reduction == 0.50

    def test_level3_caution_elevated_resting_hr(self, triage_engine: RedFlagsTriageEngine):
        """Verify resting HR elevation >= +10 bpm triggers Level 3 Caution."""
        data = TriageAssessmentInput(rhr_elevation_bpm=12)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_3_CAUTION
        assert result.action == SystemAction.REDUCE_LOAD

    def test_level3_caution_moderate_knee_pain(self, triage_engine: RedFlagsTriageEngine):
        """Verify knee pain VAS 4/10 triggers Level 3 Caution."""
        data = TriageAssessmentInput(knee_pain_vas=4)
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_3_CAUTION
        assert result.action == SystemAction.REDUCE_LOAD

    # =========================================================================
    # CAUTION RESET EVALUATION & PRIORITY TESTS
    # =========================================================================
    def test_caution_reset_conditions(self):
        """Verify Level 3 Caution Reset is allowed only after 48h rest and normalized metrics."""
        # Less than 48h rest -> reset disallowed
        assert RedFlagsTriageEngine.evaluate_caution_reset(
            hrv_z_score=0.2, knee_pain_vas=1, hours_elapsed_in_rest=24
        ) is False

        # 48h rest but HRV still low (z = -1.5) -> reset disallowed
        assert RedFlagsTriageEngine.evaluate_caution_reset(
            hrv_z_score=-1.5, knee_pain_vas=1, hours_elapsed_in_rest=48
        ) is False

        # 48h rest, recovered HRV (z > -1.0) and pain VAS <= 2 -> reset allowed
        assert RedFlagsTriageEngine.evaluate_caution_reset(
            hrv_z_score=-0.5, knee_pain_vas=1, hours_elapsed_in_rest=48
        ) is True

    def test_triage_priority_level1_overrides_all(self, triage_engine: RedFlagsTriageEngine):
        """Verify Level 1 Emergency takes absolute precedence when multiple red flags are present."""
        data = TriageAssessmentInput(
            chest_pain_or_pressure=True,   # Level 1
            hrv_z_score=-3.5,              # Level 2
            knee_pain_vas=4                # Level 3
        )
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_1_EMERGENCY
        assert result.action == SystemAction.HARD_LOCK
        assert result.call_emergency is True

    def test_level0_all_clear(self, triage_engine: RedFlagsTriageEngine):
        """Verify normal telemetry yields Level 0 Clear status."""
        data = TriageAssessmentInput()
        result = triage_engine.evaluate(data)

        assert result.triage_level == TriageLevel.LEVEL_0_CLEAR
        assert result.action == SystemAction.PROCEED
