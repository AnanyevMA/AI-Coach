"""
test_phase53_enhancements.py — Pytest suite for Phase 5.3 On-Device Hybrid SLM (Small Language Model) Fallback Service
AI Adaptive Coach v7.0
"""

import pytest
from app.services.on_device_slm_service import on_device_slm_service, OnDeviceContextPackage


def test_on_device_context_packaging():
    """Test packaging of compact context for client-side WebGPU execution."""
    package = on_device_slm_service.package_on_device_context(
        athlete_id=42,
        z_hrv=-1.8,
        acwr=1.45,
        doms=6,
        soreness_zones=["knees"],
        recent_workout_type="running"
    )

    assert isinstance(package, OnDeviceContextPackage)
    assert package.onnx_execution_config.model_name == "Gemma-2B-IT-ONNX-WebGPU"
    assert package.athlete_context["z_hrv"] == -1.8
    assert package.athlete_context["acwr"] == 1.45
    assert package.athlete_context["offline_mode"] is True
    assert "knees" in package.athlete_context["soreness_zones"]


def test_on_device_normal_context():
    """Test context packaging under optimal physiology."""
    package = on_device_slm_service.package_on_device_context(
        athlete_id=10,
        z_hrv=0.4,
        acwr=1.05,
        doms=2,
        soreness_zones=[]
    )

    assert package.athlete_context["acwr"] == 1.05
    assert package.athlete_context["doms"] == 2
    assert package.onnx_execution_config.quantization == "int4"
