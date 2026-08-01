"""
Pytest suite for AI Coach Engine (Gemini Flash), prompt context assembly,
Medical Red Flag Level 1/2 safety gating, and Pydantic plan validation.
Part of Phase 2 Test Suite for AI Adaptive Coach v7.0.
"""

import pytest
from pydantic import ValidationError

from app.medical.red_flags import TriageAssessmentInput, RedFlagsTriageEngine
from app.services.ai_coach_engine import (
    AICoachEngine,
    RedFlagBlockError,
    AICoachPlanResponse,
    WorkoutInterval,
    WorkoutSafetyAssessment,
    ai_coach_engine
)


class TestAICoachEngine:
    """Test suite for Gemini Flash AI Engine integration and safety governance."""

    @pytest.fixture
    def engine(self) -> AICoachEngine:
        return ai_coach_engine

    # =========================================================================
    # 1. PROMPT CONTEXT ASSEMBLY TESTS
    # =========================================================================
    def test_assemble_context_structure(self, engine: AICoachEngine):
        """Verify context assembly includes all physiological parameters and system prompt."""
        recent = [
            {"date": "2026-07-30", "title": "Tempo Run", "duration_min": 45, "avg_hr": 155},
            {"date": "2026-07-31", "title": "Recovery Ride", "duration_min": 30, "avg_hr": 120}
        ]

        context = engine.assemble_context(
            athlete_id=101,
            athlete_name="Иван Петров",
            max_hr=195,
            rest_hr=52,
            hrv_z_score=-0.4,
            acwr=1.15,
            doms_score=2,
            recent_workouts=recent,
            goal="Marathon Sub-3"
        )

        assert context["athlete_id"] == 101
        assert context["athlete_name"] == "Иван Петров"
        assert context["physiological_metrics"]["max_hr"] == 195
        assert context["physiological_metrics"]["rest_hr"] == 52
        assert context["physiological_metrics"]["hrv_z_score"] == -0.4
        assert context["physiological_metrics"]["acwr"] == 1.15
        assert context["physiological_metrics"]["doms_score"] == 2
        assert context["recent_workouts_count"] == 2
        assert "system_instruction" in context
        assert "AI Sports Science Coach" in context["system_instruction"]

    # =========================================================================
    # 2. MEDICAL RED FLAG BLOCKING TESTS (LEVEL 1 & LEVEL 2)
    # =========================================================================
    def test_level1_emergency_blocks_ai_generation(self, engine: AICoachEngine):
        """Verify Level 1 Emergency (chest pain) IMMEDIATELY BLOCKS plan generation."""
        triage_input = TriageAssessmentInput(chest_pain_or_pressure=True)
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Test", max_hr=190, rest_hr=60,
            hrv_z_score=0.0, acwr=1.0, doms_score=0, recent_workouts=[]
        )

        with pytest.raises(RedFlagBlockError, match="LEVEL 1 EMERGENCY LOCK"):
            engine.generate_plan(triage_input=triage_input, context=context)

    def test_level1_emergency_syncope_blocks_ai_generation(self, engine: AICoachEngine):
        """Verify Level 1 Emergency (syncope/dizziness) IMMEDIATELY BLOCKS plan generation."""
        triage_input = TriageAssessmentInput(syncope_or_dizziness=True)
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Test", max_hr=190, rest_hr=60,
            hrv_z_score=0.0, acwr=1.0, doms_score=0, recent_workouts=[]
        )

        with pytest.raises(RedFlagBlockError, match="LEVEL 1 EMERGENCY LOCK"):
            engine.generate_plan(triage_input=triage_input, context=context)

    def test_level2_medical_lock_critical_hrv_blocks_ai_generation(self, engine: AICoachEngine):
        """Verify Level 2 Medical Lock (severe HRV drop z < -3.0) BLOCKS plan generation."""
        triage_input = TriageAssessmentInput(hrv_z_score=-3.5)
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Test", max_hr=190, rest_hr=60,
            hrv_z_score=-3.5, acwr=1.0, doms_score=0, recent_workouts=[]
        )

        with pytest.raises(RedFlagBlockError, match="LEVEL 2 MEDICAL REFERRAL LOCK"):
            engine.generate_plan(triage_input=triage_input, context=context)

    def test_level2_medical_lock_fever_blocks_ai_generation(self, engine: AICoachEngine):
        """Verify Level 2 Medical Lock (fever >= 37.5°C) BLOCKS plan generation."""
        triage_input = TriageAssessmentInput(fever_celsius=38.2)
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Test", max_hr=190, rest_hr=60,
            hrv_z_score=0.0, acwr=1.0, doms_score=0, recent_workouts=[]
        )

        with pytest.raises(RedFlagBlockError, match="LEVEL 2 MEDICAL REFERRAL LOCK"):
            engine.generate_plan(triage_input=triage_input, context=context)

    # =========================================================================
    # 3. LEVEL 0 CLEAR & LEVEL 3 CAUTION PLAN GENERATION TESTS
    # =========================================================================
    def test_level0_clear_generates_standard_plan(self, engine: AICoachEngine):
        """Verify Level 0 Clear generates standard adaptive plan safely."""
        triage_input = TriageAssessmentInput()
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Athlete Clear", max_hr=190, rest_hr=55,
            hrv_z_score=0.2, acwr=1.1, doms_score=1, recent_workouts=[]
        )

        plan = engine.generate_plan(triage_input=triage_input, context=context)

        assert isinstance(plan, AICoachPlanResponse)
        assert plan.total_duration_minutes == 60
        assert plan.target_hr_zone == "Z2_ENDURANCE"
        assert plan.safety_assessment.is_safe is True
        assert len(plan.intervals) == 3

    def test_level3_caution_generates_reduced_recovery_plan(self, engine: AICoachEngine):
        """Verify Level 3 Caution (moderate HRV drop z = -1.8) generates reduced Z1 plan."""
        triage_input = TriageAssessmentInput(hrv_z_score=-1.8)
        context = engine.assemble_context(
            athlete_id=1, athlete_name="Athlete Caution", max_hr=190, rest_hr=55,
            hrv_z_score=-1.8, acwr=1.1, doms_score=3, recent_workouts=[]
        )

        plan = engine.generate_plan(triage_input=triage_input, context=context)

        assert isinstance(plan, AICoachPlanResponse)
        assert plan.total_duration_minutes == 30
        assert plan.target_hr_zone == "Z1_RECOVERY"
        assert plan.safety_assessment.risk_level == "CAUTION"

    # =========================================================================
    # 4. PYDANTIC SCHEMA VALIDATION TESTS
    # =========================================================================
    def test_pydantic_schema_validation_success(self, engine: AICoachEngine):
        """Verify valid dict parses correctly into AICoachPlanResponse Pydantic model."""
        data = {
            "plan_title": "Interval Run",
            "summary": "5x1k Vo2max intervals",
            "workout_type": "Intervals",
            "total_duration_minutes": 45,
            "target_hr_zone": "Z4_THRESHOLD",
            "safety_assessment": {
                "is_safe": True,
                "risk_level": "LOW",
                "warnings": []
            },
            "intervals": [
                {
                    "name": "Warmup",
                    "duration_minutes": 10,
                    "target_hr_zone": "Z1_RECOVERY",
                    "description": "Easy jog"
                }
            ],
            "coach_advice": "Focus on consistent pacing."
        }

        plan = AICoachPlanResponse.model_validate(data)
        assert plan.plan_title == "Interval Run"
        assert plan.total_duration_minutes == 45

    def test_pydantic_schema_validation_invalid_duration(self, engine: AICoachEngine):
        """Verify negative or excessive workout duration fails Pydantic validation."""
        invalid_data_negative = {
            "plan_title": "Invalid Plan",
            "summary": "Test",
            "workout_type": "Run",
            "total_duration_minutes": -15,
            "target_hr_zone": "Z1",
            "safety_assessment": {"is_safe": True, "risk_level": "LOW", "warnings": []},
            "intervals": [],
            "coach_advice": "Test"
        }

        with pytest.raises(ValidationError):
            AICoachPlanResponse.model_validate(invalid_data_negative)

        invalid_data_excessive = dict(invalid_data_negative, total_duration_minutes=500)
        with pytest.raises(ValidationError):
            AICoachPlanResponse.model_validate(invalid_data_excessive)
