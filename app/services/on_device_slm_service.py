"""
On-Device Hybrid SLM (Small Language Model) Service for AI Adaptive Coach v7.0.
Phase 5.3: Prepares ONNX WebGPU model execution parameters and prompt context
for 100% offline, on-device local AI adaptation (Phi-3-mini / Gemma-2B).
"""

import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("on_device_slm_service")


class OnDeviceModelConfig(BaseModel):
    model_name: str = "Gemma-2B-IT-ONNX-WebGPU"
    quantization: str = "int4"
    context_window: int = 2048
    temperature: float = 0.2
    fallback_offline_enabled: bool = True


class OnDeviceContextPackage(BaseModel):
    system_prompt: str
    athlete_context: Dict[str, Any]
    onnx_execution_config: OnDeviceModelConfig


class OnDeviceSLMService:
    """
    On-Device Hybrid SLM Manager.
    Formats light-weight system prompts and ONNX WebGPU runtime configs for PWA local inference.
    """
    def __init__(self):
        self.default_config = OnDeviceModelConfig()

    def package_on_device_context(
        self,
        athlete_id: int,
        z_hrv: float,
        acwr: float,
        doms: int,
        soreness_zones: List[str],
        recent_workout_type: str = "running",
    ) -> OnDeviceContextPackage:
        """
        Formats a compact, token-efficient system prompt and context package for client-side WebGPU execution.
        """
        system_prompt = (
            "You are an on-device AI Sports Coach running locally via WebGPU. "
            "Adapt the workout plan safely based on HRV z-score, ACWR, and DOMS score. "
            "If ACWR > 1.4 or z_hrv < -1.5, downgrade intensity to Zone 2 Active Recovery."
        )

        athlete_context = {
            "athlete_id": athlete_id,
            "z_hrv": round(z_hrv, 2),
            "acwr": round(acwr, 2),
            "doms": doms,
            "soreness_zones": soreness_zones,
            "recent_workout_type": recent_workout_type,
            "offline_mode": True,
        }

        return OnDeviceContextPackage(
            system_prompt=system_prompt,
            athlete_context=athlete_context,
            onnx_execution_config=self.default_config,
        )


on_device_slm_service = OnDeviceSLMService()
