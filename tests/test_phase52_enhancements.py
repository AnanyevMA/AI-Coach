"""
test_phase52_enhancements.py — Pytest suite for Phase 5.2 Sport-Specific EWMA ACWR, Fueling/Hydration Calculator & B2B Batch Overrides
AI Adaptive Coach v7.0
"""

import pytest
from app.services.telemetry_analysis_service import telemetry_analysis_service


def test_sport_specific_ewma_acwr():
    """Test sport strain multipliers (Running 1.3x vs Cycling 1.0x)."""
    daily_loads = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
    
    general_acwr = telemetry_analysis_service.calculate_ewma_acwr(daily_loads, sport_type="general")
    running_acwr = telemetry_analysis_service.calculate_ewma_acwr(daily_loads, sport_type="running")
    
    assert general_acwr.acute_workload < running_acwr.acute_workload
    assert running_acwr.acute_workload == pytest.approx(general_acwr.acute_workload * 1.3, rel=1e-2)


def test_fueling_and_hydration_calculator():
    """Test glycogen carbs, fluid loss, and sodium loss calculation."""
    # 2-hour workout at high intensity (IF = 0.85)
    fueling = telemetry_analysis_service.calculate_fueling_and_hydration(
        duration_seconds=7200.0,
        intensity_factor=0.85
    )
    
    assert fueling["carbs_grams"] > 100.0  # High carb demand for 2h
    assert fueling["fluid_ml"] >= 1500.0    # Sweat loss > 1.5L
    assert fueling["sodium_mg"] >= 750.0    # Electrolyte loss


def test_zero_duration_fueling():
    """Test boundary condition for 0 second duration."""
    fueling = telemetry_analysis_service.calculate_fueling_and_hydration(0.0)
    assert fueling["carbs_grams"] == 0.0
    assert fueling["fluid_ml"] == 0.0
    assert fueling["sodium_mg"] == 0.0
