"""
Pytest suite for FIT file parser, time-series metrics decoding, and intensity zone calculations.
Part of Phase 2 Test Suite for AI Adaptive Coach v7.0.
"""

import pytest
import struct
from datetime import datetime, timezone

from app.services.fit_parser import (
    FitParser,
    FitParserError,
    FitParseResult,
    FitRecord,
    HRZone,
    PowerZone,
    fit_parser_service
)


class TestFitParser:
    """Test suite for FIT telemetry file parsing and sports analytics."""

    @pytest.fixture
    def parser(self) -> FitParser:
        return fit_parser_service

    # =========================================================================
    # 1. BINARY FIT DECODING & METRIC EXTRACTION TESTS
    # =========================================================================
    def test_parse_valid_binary_fit_file(self, parser: FitParser):
        """Verify binary .FIT file header decoding and record extraction."""
        binary_data = parser.create_mock_fit_binary(
            num_records=20,
            base_hr=145,
            base_cadence=88,
            base_power=210.0
        )
        result = parser.parse_bytes(binary_data, athlete_max_hr=190, athlete_ftp=250.0)

        assert result.is_valid is True
        assert len(result.records) == 20
        assert result.avg_hr is not None and result.avg_hr >= 145.0
        assert result.max_hr is not None and result.max_hr >= 145
        assert result.avg_cadence is not None and result.avg_cadence >= 88.0
        assert result.avg_power is not None and result.avg_power >= 210.0
        assert result.duration_seconds == 95.0  # (20 - 1) * 5 seconds

    def test_parse_time_series_record_timestamps(self, parser: FitParser):
        """Verify decoded time-series record timestamps are strictly sequential."""
        binary_data = parser.create_mock_fit_binary(num_records=10)
        result = parser.parse_bytes(binary_data)

        timestamps = [r.timestamp for r in result.records]
        assert len(timestamps) == 10
        for i in range(len(timestamps) - 1):
            assert timestamps[i + 1] > timestamps[i]

    # =========================================================================
    # 2. INTENSITY ZONE CALCULATION TESTS (HR & POWER)
    # =========================================================================
    def test_calculate_hr_zones_distribution(self, parser: FitParser):
        """Verify heart rate zone percentage distribution calculation across Z1-Z5."""
        max_hr = 200
        # 100 hrs: 20 in Z1 (<120), 20 in Z2 (120-139), 20 in Z3 (140-159), 20 in Z4 (160-179), 20 in Z5 (>=180)
        hrs = [110] * 20 + [130] * 20 + [150] * 20 + [170] * 20 + [185] * 20

        dist = parser.calculate_hr_zones(hrs, max_hr=max_hr)

        assert dist[HRZone.Z1_RECOVERY.value] == 20.0
        assert dist[HRZone.Z2_ENDURANCE.value] == 20.0
        assert dist[HRZone.Z3_TEMPO.value] == 20.0
        assert dist[HRZone.Z4_THRESHOLD.value] == 20.0
        assert dist[HRZone.Z5_ANAEROBIC.value] == 20.0

    def test_calculate_power_zones_distribution(self, parser: FitParser):
        """Verify Coggan power zones calculation based on athlete FTP."""
        ftp = 200.0
        # 100 watts samples:
        # 100w (50% FTP) -> Z1
        # 140w (70% FTP) -> Z2
        # 170w (85% FTP) -> Z3
        # 200w (100% FTP) -> Z4
        # 230w (115% FTP) -> Z5
        # 260w (130% FTP) -> Z6
        powers = [100.0] * 15 + [140.0] * 25 + [170.0] * 20 + [200.0] * 20 + [230.0] * 10 + [260.0] * 10

        dist = parser.calculate_power_zones(powers, ftp=ftp)

        assert dist[PowerZone.Z1_RECOVERY.value] == 15.0
        assert dist[PowerZone.Z2_ENDURANCE.value] == 25.0
        assert dist[PowerZone.Z3_TEMPO.value] == 20.0
        assert dist[PowerZone.Z4_THRESHOLD.value] == 20.0
        assert dist[PowerZone.Z5_VO2MAX.value] == 10.0
        assert dist[PowerZone.Z6_ANAEROBIC.value] == 10.0

    def test_zones_with_empty_or_zero_values(self, parser: FitParser):
        """Verify zone calculations handle empty telemetry lists gracefully."""
        hr_dist = parser.calculate_hr_zones([], max_hr=190)
        power_dist = parser.calculate_power_zones([], ftp=250.0)

        assert all(val == 0.0 for val in hr_dist.values())
        assert all(val == 0.0 for val in power_dist.values())

    # =========================================================================
    # 3. CORRUPTED FILE & EDGE CASE TESTING
    # =========================================================================
    def test_corrupted_fit_header_raises_error(self, parser: FitParser):
        """Verify error is raised when header size is corrupted or magic bytes mismatch."""
        invalid_magic_bytes = b"\x0e\x20\x34\x08\x00\x00\x00\x00BADM\x00\x00"
        with pytest.raises(FitParserError, match="Invalid FIT header magic bytes"):
            parser.parse_bytes(invalid_magic_bytes)

    def test_truncated_file_content_raises_error(self, parser: FitParser):
        """Verify error is raised when file byte size is less than 14 bytes."""
        short_bytes = b"\x0e\x20\x00"
        with pytest.raises(FitParserError, match="Corrupted or incomplete FIT file header"):
            parser.parse_bytes(short_bytes)

    def test_empty_payload_after_header(self, parser: FitParser):
        """Verify parsing header with data size 0 returns valid empty result."""
        header = struct.pack("<BBHI4sH", 14, 0x20, 2100, 0, b".FIT", 0x0000)
        result = parser.parse_bytes(header)

        assert result.is_valid is True
        assert len(result.records) == 0
        assert result.error_message is not None
        assert "no valid data records" in result.error_message
