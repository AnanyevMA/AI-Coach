"""
AI Coach Engine (Gemini Flash & Pro) for AI Adaptive Coach v7.0.
Handles athlete context assembly (profile, knee injury/VAS, telemetry, Hooper index),
safety gating via RedFlagsTriageEngine, and Pydantic schema validation for AI-generated training plans.
"""

import json
import logging
import os
from typing import List, Dict, Optional, Any, Union
import httpx
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.medical.red_flags import (
    RedFlagsTriageEngine,
    TriageAssessmentInput,
    TriageLevel,
    TriageResult,
    SystemAction,
)

logger = logging.getLogger(__name__)

# Try importing google.genai SDK if available
try:
    from google import genai
    from google.genai import types
    HAS_GOOGLE_GENAI_SDK = True
except ImportError:
    HAS_GOOGLE_GENAI_SDK = False


class WorkoutInterval(BaseModel):
    name: str
    duration_minutes: int
    target_hr_zone: str
    target_power_watts: Optional[float] = None
    target_cadence_rpm: Optional[int] = None
    description: str


class WorkoutSafetyAssessment(BaseModel):
    is_safe: bool
    risk_level: str  # LOW, MODERATE, CAUTION, HIGH
    warnings: List[str] = Field(default_factory=list)


class AICoachPlanResponse(BaseModel):
    plan_title: str
    summary: str
    workout_type: str
    total_duration_minutes: int
    target_hr_zone: str
    safety_assessment: WorkoutSafetyAssessment
    intervals: List[WorkoutInterval]
    coach_advice: str

    @field_validator("total_duration_minutes")
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Workout duration must be positive.")
        if v > 360:
            raise ValueError("Single workout duration cannot exceed 360 minutes.")
        return v


class ActivityAnalysisResponse(BaseModel):
    activity_title: str
    compliance_score: float  # 0.0 - 100.0%
    physiological_impact: str
    rpe_vs_hr_alignment: str
    adaptation_recommendation: str
    safety_flags_detected: List[str] = Field(default_factory=list)
    coaching_summary: str


class AICoachEngineError(Exception):
    """Exception raised when AI Coach Engine fails or is unsafe."""
    pass


class RedFlagBlockError(AICoachEngineError):
    """Exception raised when Red Flag triggers block plan generation."""
    pass


class AICoachEngine:
    """
    Core AI Adaptive Coach Engine powered by Gemini 1.5 Flash (default) with optional fallback to Gemini 1.5 Pro.
    Enforces strict sports medicine red flag gating BEFORE LLM requests and Pydantic schema validation AFTER.
    """

    def __init__(
        self,
        triage_engine: Optional[RedFlagsTriageEngine] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        self.triage_engine = triage_engine or RedFlagsTriageEngine()
        self.primary_model = primary_model or getattr(settings, "GEMINI_PRIMARY_MODEL", "gemini-1.5-flash")
        self.fallback_model = fallback_model or getattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-1.5-pro")

    def _get_api_key(self) -> Optional[str]:
        return (
            getattr(settings, "GEMINI_API_KEY", None)
            or getattr(settings, "GOOGLE_API_KEY", None)
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )

    def assemble_context(
        self,
        athlete_id: int,
        athlete_name: str,
        max_hr: int,
        rest_hr: int,
        hrv_z_score: float,
        acwr: float,
        doms_score: int,
        recent_workouts: List[Dict[str, Any]],
        goal: str = "Endurance & Speed",
        knee_pain_vas: int = 0,
        rhr_elevation_bpm: int = 0,
        medical_notes: Optional[str] = None,
        hooper_survey: Optional[Dict[str, int]] = None,
        date_of_birth: Optional[str] = None,
        height_cm: Optional[float] = None,
        weight_kg: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Assembles athlete profile, knee injury status, telemetry, and subjective Hooper Questionnaire into structured prompt context.
        """
        hooper_data = hooper_survey or {}
        sleep_q = hooper_data.get("sleep", hooper_data.get("sleep_quality", 1))
        stress_l = hooper_data.get("stress", hooper_data.get("stress_level", 1))
        fatigue_l = hooper_data.get("fatigue", hooper_data.get("fatigue_level", 1))
        doms_l = hooper_data.get("doms", doms_score if doms_score > 0 else 1)

        hooper_total = sleep_q + stress_l + fatigue_l + doms_l

        physiological_metrics = {
            "max_hr": max_hr,
            "rest_hr": rest_hr,
            "hrv_z_score": round(hrv_z_score, 2),
            "acwr": round(acwr, 2),
            "doms_score": doms_score or doms_l,
            "knee_pain_vas": knee_pain_vas,
            "rhr_elevation_bpm": rhr_elevation_bpm,
        }

        subjective_hooper = {
            "sleep_quality_1_7": sleep_q,
            "stress_level_1_7": stress_l,
            "fatigue_level_1_7": fatigue_l,
            "doms_level_1_7": doms_l,
            "total_hooper_index": hooper_total,
        }

        profile_summary = {
            "date_of_birth": date_of_birth,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "medical_notes": medical_notes or "No acute chronic conditions reported",
            "knee_injury_status": f"Knee pain VAS {knee_pain_vas}/10" if knee_pain_vas > 0 else "No knee pain reported",
        }

        return {
            "athlete_id": athlete_id,
            "athlete_name": athlete_name,
            "athlete_profile": profile_summary,
            "physiological_metrics": physiological_metrics,
            "subjective_hooper_questionnaire": subjective_hooper,
            "recent_workouts_count": len(recent_workouts),
            "recent_workouts_summary": recent_workouts[:5],
            "goal": goal,
            "system_instruction": (
                "You are an AI Sports Science Coach. Design an adaptive workout plan strictly compliant "
                "with physiological readiness, HRV z-score, and sports medicine safety boundaries."
            ),
        }

    def generate_plan(
        self,
        triage_input: TriageAssessmentInput,
        context: Dict[str, Any],
        raw_llm_json_override: Optional[Dict[str, Any]] = None,
    ) -> AICoachPlanResponse:
        """
        Generates an adaptive training plan for an athlete.
        FIRST evaluates Red Flag safety triage. If Level 1 (Emergency) or Level 2 (Medical Lock) triggers are detected,
        the request to Gemini LLM is IMMEDIATELY BLOCKED to ensure safety.
        """
        # Step 1: Enforce Medical Red Flag Triage BEFORE LLM Call
        triage_result = self.triage_engine.evaluate(triage_input)

        if triage_result.triage_level == TriageLevel.LEVEL_1_EMERGENCY:
            raise RedFlagBlockError(
                f"LEVEL 1 EMERGENCY LOCK: {triage_result.message}"
            )

        if triage_result.triage_level == TriageLevel.LEVEL_2_MEDICAL_REFERRAL:
            raise RedFlagBlockError(
                f"LEVEL 2 MEDICAL REFERRAL LOCK: {triage_result.message}"
            )

        # Step 2: Use override if passed (for deterministic unit tests or offline simulation)
        if raw_llm_json_override:
            raw_data = raw_llm_json_override
        else:
            api_key = self._get_api_key()
            if api_key:
                raw_data = self._generate_with_gemini(context, triage_result)
            else:
                raw_data = self._generate_fallback_dict(context, triage_result)

        # Step 3: Pydantic Schema Validation
        return AICoachPlanResponse.model_validate(raw_data)

    def analyze_activity(
        self,
        activity_data: Dict[str, Any],
        plan_data: Optional[Dict[str, Any]] = None,
        athlete_context: Optional[Dict[str, Any]] = None,
    ) -> ActivityAnalysisResponse:
        """
        Analyzes executed workout activity against planned targets and readiness context.
        """
        api_key = self._get_api_key()
        if api_key:
            try:
                raw_analysis = self._analyze_with_gemini(activity_data, plan_data, athlete_context)
                if raw_analysis:
                    return ActivityAnalysisResponse.model_validate(raw_analysis)
            except Exception as e:
                logger.warning(f"Gemini activity analysis failed, falling back to rule engine: {e}")

        # Deterministic offline analysis
        duration_planned = plan_data.get("total_duration_minutes", 60) * 60 if plan_data else 3600
        duration_actual = activity_data.get("duration_seconds", 3600)
        dur_diff = abs(duration_actual - duration_planned) / max(1, duration_planned)
        compliance = max(0.0, min(100.0, (1.0 - dur_diff) * 100.0))

        avg_hr = activity_data.get("avg_hr", 145)
        max_hr = activity_data.get("max_hr", 170)
        rpe = activity_data.get("rpe_score", 6)

        flags = []
        if max_hr and max_hr > 195:
            flags.append(f"High peak heart rate recorded ({max_hr} bpm)")
        if rpe and rpe >= 9:
            flags.append(f"Near-maximal perceived effort RPE {rpe}/10")

        return ActivityAnalysisResponse(
            activity_title=activity_data.get("title", "Completed Workout"),
            compliance_score=round(compliance, 1),
            physiological_impact="Moderate Aerobic Stimulus" if avg_hr and avg_hr < 155 else "High Metabolic & Cardiovascular Load",
            rpe_vs_hr_alignment="Aligned" if rpe and 5 <= rpe <= 8 else "Discrepancy detected between subjective RPE and HR telemetry",
            adaptation_recommendation="Maintain planned recovery protocol. Zone 2 active recovery recommended for next session.",
            safety_flags_detected=flags,
            coaching_summary="Solid execution of workout session. Telemetry metrics show appropriate aerobic response."
        )

    def _generate_with_gemini(
        self,
        context: Dict[str, Any],
        triage_result: TriageResult
    ) -> Dict[str, Any]:
        """
        Call Gemini API (Primary model: gemini-1.5-flash, Fallback: gemini-1.5-pro).
        """
        prompt = self._build_gemini_prompt(context, triage_result)

        # Try Primary Model
        try:
            res_json = self._call_gemini_model(self.primary_model, prompt)
            if res_json:
                return res_json
        except Exception as e:
            logger.warning(f"Primary model {self.primary_model} failed: {e}. Trying fallback model {self.fallback_model}")

        # Try Fallback Model
        try:
            res_json = self._call_gemini_model(self.fallback_model, prompt)
            if res_json:
                return res_json
        except Exception as e:
            logger.error(f"Fallback model {self.fallback_model} failed: {e}. Using deterministic fallback.")

        return self._generate_fallback_dict(context, triage_result)

    def mask_api_key(self, key: Optional[str] = None) -> str:
        """Mask Gemini API key to protect against secret leakage in logs/UI."""
        k = key or self._get_api_key()
        if not k:
            return "NOT_SET"
        if len(k) <= 8:
            return "****"
        return f"{k[:4]}...{k[-4:]}"

    def _call_gemini_model(self, model_name: str, prompt: str) -> Optional[Dict[str, Any]]:
        api_key = self._get_api_key()
        if not api_key:
            return None

        # Use google-genai SDK if available
        if HAS_GOOGLE_GENAI_SDK:
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    )
                )
                if response and response.text:
                    return json.loads(response.text)
            except Exception as e:
                logger.warning(f"google-genai SDK call failed: {e}")

        # Secure HTTP call to Google Gemini REST API: Pass API key via x-goog-api-key header (prevents URL query string leakage)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    return json.loads(text)
        except Exception as e:
            # Mask API key in any error log
            masked_key = self.mask_api_key(api_key)
            logger.error(f"Gemini REST call failed for model {model_name} (key: {masked_key}): {e}")
        return None

    def _analyze_with_gemini(
        self,
        activity_data: Dict[str, Any],
        plan_data: Optional[Dict[str, Any]],
        athlete_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        prompt = (
            "You are an AI Sports Scientist. Analyze the executed workout against planned parameters.\n"
            f"Executed Activity: {json.dumps(activity_data)}\n"
            f"Planned Workout: {json.dumps(plan_data or {})}\n"
            f"Athlete Context: {json.dumps(athlete_context or {})}\n\n"
            "Respond strictly in JSON matching schema:\n"
            "{\n"
            '  "activity_title": "string",\n'
            '  "compliance_score": float (0-100),\n'
            '  "physiological_impact": "string",\n'
            '  "rpe_vs_hr_alignment": "string",\n'
            '  "adaptation_recommendation": "string",\n'
            '  "safety_flags_detected": ["string"],\n'
            '  "coaching_summary": "string"\n'
            "}"
        )
        res = self._call_gemini_model(self.primary_model, prompt)
        if not res:
            res = self._call_gemini_model(self.fallback_model, prompt)
        return res or {}

    def _build_gemini_prompt(self, context: Dict[str, Any], triage_result: TriageResult) -> str:
        return (
            f"System Instruction: {context.get('system_instruction')}\n\n"
            f"Athlete Context:\n{json.dumps(context, indent=2)}\n\n"
            f"Triage Assessment: {triage_result.triage_level.value} - {triage_result.message}\n\n"
            "Generate a structured workout plan JSON matching schema:\n"
            "{\n"
            '  "plan_title": "string",\n'
            '  "summary": "string",\n'
            '  "workout_type": "string",\n'
            '  "total_duration_minutes": integer,\n'
            '  "target_hr_zone": "string (e.g. Z1_RECOVERY, Z2_ENDURANCE, Z3_TEMPO, Z4_THRESHOLD)",\n'
            '  "safety_assessment": {\n'
            '    "is_safe": boolean,\n'
            '    "risk_level": "LOW" | "MODERATE" | "CAUTION" | "HIGH",\n'
            '    "warnings": ["string"]\n'
            '  },\n'
            '  "intervals": [\n'
            '    {\n'
            '      "name": "string",\n'
            '      "duration_minutes": integer,\n'
            '      "target_hr_zone": "string",\n'
            '      "target_power_watts": float or null,\n'
            '      "target_cadence_rpm": integer or null,\n'
            '      "description": "string"\n'
            '    }\n'
            '  ],\n'
            '  "coach_advice": "string"\n'
            "}"
        )

    def _generate_fallback_dict(self, context: Dict[str, Any], triage_result: TriageResult) -> Dict[str, Any]:
        is_caution = (triage_result.triage_level == TriageLevel.LEVEL_3_CAUTION)
        duration = 30 if is_caution else 60
        zone = "Z1_RECOVERY" if is_caution else "Z2_ENDURANCE"

        return {
            "plan_title": "Adaptive Recovery Run" if is_caution else "Base Endurance Ride",
            "summary": "Reduced load due to Caution status" if is_caution else "Standard aerobic zone training",
            "workout_type": "Recovery" if is_caution else "Endurance",
            "total_duration_minutes": duration,
            "target_hr_zone": zone,
            "safety_assessment": {
                "is_safe": True,
                "risk_level": "CAUTION" if is_caution else "LOW",
                "warnings": [triage_result.message] if is_caution else []
            },
            "intervals": [
                {
                    "name": "Warmup",
                    "duration_minutes": 10,
                    "target_hr_zone": "Z1_RECOVERY",
                    "target_cadence_rpm": 85,
                    "description": "Easy warmup spinning"
                },
                {
                    "name": "Main Set",
                    "duration_minutes": duration - 15,
                    "target_hr_zone": zone,
                    "target_cadence_rpm": 90,
                    "description": "Steady aerobic effort"
                },
                {
                    "name": "Cooldown",
                    "duration_minutes": 5,
                    "target_hr_zone": "Z1_RECOVERY",
                    "target_cadence_rpm": 80,
                    "description": "Easy spinning cooldown"
                }
            ],
            "coach_advice": "Focus on smooth cadence and stay well hydrated."
        }


ai_coach_engine = AICoachEngine()
