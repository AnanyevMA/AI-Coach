"""
Unit tests for FIT/GPX/TCX parser service and Telemetry Analysis Service.
"""

from datetime import datetime, timezone
import math
import pytest

from app.services.fit_parser_service import (
    FITParserService,
    fit_parser_service,
    ParsedActivity,
    TelemetryPoint,
    LapData,
)
from app.services.telemetry_analysis_service import (
    TelemetryAnalysisService,
    telemetry_analysis_service,
    NormalizedPowerResult,
    ImpulseMetrics,
    ACWRResult,
    HRVZScoreResult,
)


# ==============================================================================
# FIT / GPX / TCX Parser Service Tests
# ==============================================================================

def test_generate_simulated_activity():
    parser = FITParserService()
    activity = parser.generate_simulated_activity(
        activity_type="running",
        duration_seconds=600,
    )

    assert isinstance(activity, ParsedActivity)
    assert activity.activity_type == "running"
    assert activity.duration_seconds == 600.0
    assert activity.is_simulated is True
    assert len(activity.records) == 600
    assert len(activity.laps) == 2  # 2 x 300s laps
    assert activity.avg_hr is not None and activity.avg_hr > 0
    assert activity.max_hr is not None and activity.max_hr >= activity.avg_hr
    assert activity.avg_power is not None and activity.avg_power > 0
    assert activity.avg_speed is not None and activity.avg_speed > 0


def test_parse_gpx_bytes():
    gpx_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="Test" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
      <trk>
        <name>Morning Run</name>
        <type>running</type>
        <trkseg>
          <trkpt lat="55.7558" lon="37.6173">
            <ele>150.0</ele>
            <time>2026-08-01T10:00:00Z</time>
            <extensions>
              <gpxtpx:TrackPointExtension>
                <gpxtpx:hr>140</gpxtpx:hr>
                <gpxtpx:cad>175</gpxtpx:cad>
              </gpxtpx:TrackPointExtension>
            </extensions>
          </trkpt>
          <trkpt lat="55.7560" lon="37.6175">
            <ele>152.0</ele>
            <time>2026-08-01T10:00:10Z</time>
            <extensions>
              <gpxtpx:TrackPointExtension>
                <gpxtpx:hr>145</gpxtpx:hr>
                <gpxtpx:cad>178</gpxtpx:cad>
              </gpxtpx:TrackPointExtension>
            </extensions>
          </trkpt>
        </trkseg>
      </trk>
    </gpx>"""

    parser = FITParserService()
    activity = parser.parse_gpx_bytes(gpx_xml)

    assert activity.activity_type == "running"
    assert len(activity.records) == 2
    assert activity.records[0].heart_rate == 140
    assert activity.records[0].cadence == 175
    assert activity.records[0].altitude == 150.0
    assert activity.records[1].heart_rate == 145
    assert activity.duration_seconds == 10.0
    assert activity.total_elevation_gain == 2.0


def test_parse_tcx_bytes():
    tcx_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
      <Activities>
        <Activity Sport="Biking">
          <Id>2026-08-01T10:00:00Z</Id>
          <Lap StartTime="2026-08-01T10:00:00Z">
            <TotalTimeSeconds>120</TotalTimeSeconds>
            <DistanceMeters>1000</DistanceMeters>
            <AverageHeartRateBpm><Value>150</Value></AverageHeartRateBpm>
            <MaximumHeartRateBpm><Value>165</Value></MaximumHeartRateBpm>
            <Track>
              <Trackpoint>
                <Time>2026-08-01T10:00:00Z</Time>
                <Position>
                  <LatitudeDegrees>55.7558</LatitudeDegrees>
                  <LongitudeDegrees>37.6173</LongitudeDegrees>
                </Position>
                <AltitudeMeters>100</AltitudeMeters>
                <HeartRateBpm><Value>148</Value></HeartRateBpm>
                <Cadence>90</Cadence>
                <Extensions>
                  <Watts>250</Watts>
                </Extensions>
              </Trackpoint>
              <Trackpoint>
                <Time>2026-08-01T10:02:00Z</Time>
                <Position>
                  <LatitudeDegrees>55.7600</LatitudeDegrees>
                  <LongitudeDegrees>37.6200</LongitudeDegrees>
                </Position>
                <AltitudeMeters>105</AltitudeMeters>
                <HeartRateBpm><Value>155</Value></HeartRateBpm>
                <Cadence>92</Cadence>
                <Extensions>
                  <Watts>260</Watts>
                </Extensions>
              </Trackpoint>
            </Track>
          </Lap>
        </Activity>
      </Activities>
    </TrainingCenterDatabase>"""

    parser = FITParserService()
    activity = parser.parse_tcx_bytes(tcx_xml)

    assert activity.activity_type == "biking"
    assert len(activity.laps) == 1
    assert activity.laps[0].duration_seconds == 120.0
    assert activity.laps[0].avg_hr == 150
    assert len(activity.records) == 2
    assert activity.records[0].power == 250.0
    assert activity.records[1].power == 260.0


def test_parse_fit_fallback():
    parser = FITParserService()
    # Sending dummy binary content should trigger fallback simulation gracefully
    dummy_fit = b"\x0e\x10\x43\x00\x00\x00\x00\x00.FIT\x00\x00"
    activity = parser.parse_fit_bytes(dummy_fit)

    assert isinstance(activity, ParsedActivity)
    assert activity.is_simulated is True
    assert len(activity.records) > 0


# ==============================================================================
# Telemetry Analysis Service Tests
# ==============================================================================

def test_calculate_normalized_power():
    service = TelemetryAnalysisService()
    # Constant 200W for 60 seconds
    power_series = [200.0] * 60
    np_res = service.calculate_normalized_power(power_series, ftp=250.0)

    assert isinstance(np_res, NormalizedPowerResult)
    assert np_res.normalized_power == 200.0
    assert np_res.intensity_factor == 0.8  # 200 / 250
    assert np_res.variability_index == 1.0

    # Variable power: 100W for 30s, then 300W for 30s
    var_power = [100.0] * 30 + [300.0] * 30
    np_var = service.calculate_normalized_power(var_power, ftp=250.0)
    # NP for variable power should exceed raw average (200W)
    assert np_var.normalized_power >= 200.0
    assert np_var.variability_index >= 1.0


def test_calculate_trimp_and_tss():
    service = TelemetryAnalysisService()
    # 1 hour (3600s) activity at constant 150 bpm HR
    hr_series = [150] * 3600
    trimp = service.calculate_trimp(hr_series, rest_hr=60.0, max_hr=190.0, is_male=True)
    assert trimp > 0.0

    # 1 hour at NP = 250W with FTP = 250W -> IF = 1.0 -> TSS should be 100.0
    tss = service.calculate_tss(duration_seconds=3600.0, normalized_power=250.0, ftp=250.0)
    assert tss == 100.0


def test_calculate_ewma_acwr():
    service = TelemetryAnalysisService()

    # Steady daily load of 50 TSS for 30 days
    daily_loads = [50.0] * 30
    acwr_res = service.calculate_ewma_acwr(daily_loads, lambda_a=0.25, lambda_c=0.069)

    assert isinstance(acwr_res, ACWRResult)
    assert acwr_res.acute_workload == 50.0
    assert acwr_res.chronic_workload == 50.0
    assert acwr_res.acwr == 1.0
    assert acwr_res.risk_level == "OPTIMAL"

    # Sudden spike in acute load
    spiked_loads = [50.0] * 28 + [200.0, 200.0]
    spiked_acwr = service.calculate_ewma_acwr(spiked_loads, lambda_a=0.25, lambda_c=0.069)
    assert spiked_acwr.acwr > 1.3
    assert spiked_acwr.risk_level in ["CAUTION", "HIGH_RISK"]


def test_calculate_hrv_z_score():
    service = TelemetryAnalysisService()
    # Baseline mean 30d of ln(rMSSD) = 3.91 (rMSSD ~50ms), std_30d = 0.1
    # 7-day rMSSD = 50ms -> ln(50) = 3.912 -> z_score ~ 0.0
    z_res = service.calculate_hrv_z_score(rmssd_7d=50.0, mean_30d=3.912, std_30d=0.1)

    assert isinstance(z_res, HRVZScoreResult)
    assert abs(z_res.z_score) < 0.1
    assert z_res.status == "NORMAL"

    # Severe drop: 7-day rMSSD = 20ms -> ln(20) = 2.995 -> z_score ~ -9.17
    z_drop = service.calculate_hrv_z_score(rmssd_7d=20.0, mean_30d=3.912, std_30d=0.1)
    assert z_drop.z_score < -1.5
    assert z_drop.status == "DEPRESSED_FATIGUE"


def test_calculate_zone_distributions():
    service = TelemetryAnalysisService()
    hr_series = [100] * 100 + [130] * 100 + [160] * 100 + [180] * 100
    zones = service.calculate_hr_zone_distribution(hr_series, max_hr=200)

    assert len(zones) == 5
    total_pct = sum(z.percentage for z in zones)
    assert abs(total_pct - 100.0) < 0.5

    power_series = [100.0] * 100 + [200.0] * 100 + [300.0] * 100
    p_zones = service.calculate_power_zone_distribution(power_series, ftp=250.0)
    assert len(p_zones) == 5


def test_heart_rate_drift_and_power_curve():
    service = TelemetryAnalysisService()
    # First half: power=200W, HR=140 bpm -> EF = 200/140 = 1.428
    # Second half: power=200W, HR=154 bpm -> EF = 200/154 = 1.298 (10% drift)
    hr_series = [140] * 300 + [154] * 300
    power_series = [200.0] * 600

    drift = service.calculate_heart_rate_drift(hr_series, power_series)
    assert drift is not None
    assert drift > 5.0  # Decoupling > 5%

    curve = service.calculate_power_curve(power_series, durations=[1, 5, 60, 300])
    assert curve[1] == 200.0
    assert curve[300] == 200.0
