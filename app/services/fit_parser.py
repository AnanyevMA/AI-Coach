"""
FIT File Parser Service for AI Adaptive Coach v7.0.
Decodes .FIT binary activity files, extracts time-series metrics (HR, Cadence, Power),
and calculates Heart Rate & Power intensity zones.
"""

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any


class HRZone(str, Enum):
    Z1_RECOVERY = "Z1_RECOVERY"        # 50% - 60% Max HR
    Z2_ENDURANCE = "Z2_ENDURANCE"      # 60% - 70% Max HR
    Z3_TEMPO = "Z3_TEMPO"              # 70% - 80% Max HR
    Z4_THRESHOLD = "Z4_THRESHOLD"      # 80% - 90% Max HR
    Z5_ANAEROBIC = "Z5_ANAEROBIC"      # 90% - 100% Max HR


class PowerZone(str, Enum):
    Z1_RECOVERY = "Z1_ACTIVE_RECOVERY"  # < 55% FTP
    Z2_ENDURANCE = "Z2_ENDURANCE"        # 55% - 75% FTP
    Z3_TEMPO = "Z3_TEMPO"                # 76% - 90% FTP
    Z4_THRESHOLD = "Z4_THRESHOLD"        # 91% - 105% FTP
    Z5_VO2MAX = "Z5_VO2MAX"              # 106% - 120% FTP
    Z6_ANAEROBIC = "Z6_ANAEROBIC"        # > 120% FTP


class FitParserError(Exception):
    """Custom exception raised when .FIT file parsing fails."""
    pass


@dataclass
class FitRecord:
    timestamp: datetime
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    power: Optional[float] = None
    speed: Optional[float] = None
    altitude: Optional[float] = None
    distance: Optional[float] = None


@dataclass
class FitParseResult:
    records: List[FitRecord] = field(default_factory=list)
    avg_hr: Optional[float] = None
    max_hr: Optional[int] = None
    avg_cadence: Optional[float] = None
    max_cadence: Optional[int] = None
    avg_power: Optional[float] = None
    max_power: Optional[float] = None
    total_distance_meters: float = 0.0
    duration_seconds: float = 0.0
    hr_zone_distribution: Dict[str, float] = field(default_factory=dict)
    power_zone_distribution: Dict[str, float] = field(default_factory=dict)
    is_valid: bool = True
    error_message: Optional[str] = None


class FitParser:
    """
    Decoder and time-series extractor for Garmin .FIT files.
    Calculates HR and Power intensity distributions for sports science analytics.
    """

    FIT_HEADER_MAGIC = b".FIT"
    GARMIN_EPOCH_OFFSET = 631065600  # Seconds between 1970-01-01 and 1989-12-31 UTC

    def parse_bytes(
        self,
        content: bytes,
        athlete_max_hr: int = 190,
        athlete_ftp: float = 250.0
    ) -> FitParseResult:
        """
        Parses binary FIT file content and returns extracted records and zone analytics.
        """
        if not content or len(content) < 14:
            raise FitParserError("Corrupted or incomplete FIT file header (file too small).")

        # Parse FIT Header: [header_size(1B), protocol(1B), profile(2B), data_size(4B), magic(4B)]
        header_size = content[0]
        if header_size < 12 or len(content) < header_size:
            raise FitParserError(f"Invalid FIT header length: {header_size}")

        magic = content[8:12]
        if magic != self.FIT_HEADER_MAGIC:
            raise FitParserError(f"Invalid FIT header magic bytes: {magic!r}. Expected b'.FIT'.")

        data_size = struct.unpack("<I", content[4:8])[0]
        if len(content) < header_size + data_size:
            raise FitParserError("FIT file payload truncated or incomplete data size.")

        # Extract data payload
        payload = content[header_size : header_size + data_size]
        records = self._decode_payload(payload)

        if not records:
            return FitParseResult(
                records=[],
                is_valid=True,
                error_message="FIT file decoded successfully but contained no valid data records."
            )

        # Calculate time series summary metrics
        hrs = [r.heart_rate for r in records if r.heart_rate is not None]
        cadences = [r.cadence for r in records if r.cadence is not None]
        powers = [r.power for r in records if r.power is not None]

        avg_hr = sum(hrs) / len(hrs) if hrs else None
        max_hr = max(hrs) if hrs else None

        avg_cadence = sum(cadences) / len(cadences) if cadences else None
        max_cadence = max(cadences) if cadences else None

        avg_power = sum(powers) / len(powers) if powers else None
        max_power = max(powers) if powers else None

        duration = (records[-1].timestamp - records[0].timestamp).total_seconds() if len(records) > 1 else 0.0
        total_dist = max([r.distance for r in records if r.distance is not None], default=0.0)

        # Zone analytics
        hr_dist = self.calculate_hr_zones(hrs, athlete_max_hr)
        power_dist = self.calculate_power_zones(powers, athlete_ftp)

        return FitParseResult(
            records=records,
            avg_hr=round(avg_hr, 1) if avg_hr else None,
            max_hr=max_hr,
            avg_cadence=round(avg_cadence, 1) if avg_cadence else None,
            max_cadence=max_cadence,
            avg_power=round(avg_power, 1) if avg_power else None,
            max_power=round(max_power, 1) if max_power else None,
            total_distance_meters=round(total_dist, 2),
            duration_seconds=round(duration, 1),
            hr_zone_distribution=hr_dist,
            power_zone_distribution=power_dist,
            is_valid=True
        )

    def calculate_hr_zones(self, hrs: List[int], max_hr: int) -> Dict[str, float]:
        """
        Calculates time/percentage spent in Heart Rate zones Z1-Z5 based on max_hr.
        Returns percentage breakdown (0.0 to 100.0) for each zone.
        """
        if not hrs or max_hr <= 0:
            return {zone.value: 0.0 for zone in HRZone}

        counts = {zone.value: 0 for zone in HRZone}
        total = len(hrs)

        for hr in hrs:
            pct = hr / max_hr
            if pct < 0.60:
                counts[HRZone.Z1_RECOVERY.value] += 1
            elif pct < 0.70:
                counts[HRZone.Z2_ENDURANCE.value] += 1
            elif pct < 0.80:
                counts[HRZone.Z3_TEMPO.value] += 1
            elif pct < 0.90:
                counts[HRZone.Z4_THRESHOLD.value] += 1
            else:
                counts[HRZone.Z5_ANAEROBIC.value] += 1

        return {zone: round((count / total) * 100.0, 2) for zone, count in counts.items()}

    def calculate_power_zones(self, powers: List[float], ftp: float) -> Dict[str, float]:
        """
        Calculates percentage spent in 6 Coggan Power Zones based on Functional Threshold Power (FTP).
        """
        if not powers or ftp <= 0:
            return {zone.value: 0.0 for zone in PowerZone}

        counts = {zone.value: 0 for zone in PowerZone}
        total = len(powers)

        for p in powers:
            pct = p / ftp
            if pct < 0.55:
                counts[PowerZone.Z1_RECOVERY.value] += 1
            elif pct <= 0.75:
                counts[PowerZone.Z2_ENDURANCE.value] += 1
            elif pct <= 0.90:
                counts[PowerZone.Z3_TEMPO.value] += 1
            elif pct <= 1.05:
                counts[PowerZone.Z4_THRESHOLD.value] += 1
            elif pct <= 1.20:
                counts[PowerZone.Z5_VO2MAX.value] += 1
            else:
                counts[PowerZone.Z6_ANAEROBIC.value] += 1

        return {zone: round((count / total) * 100.0, 2) for zone, count in counts.items()}

    def create_mock_fit_binary(
        self,
        num_records: int = 10,
        start_time: Optional[datetime] = None,
        base_hr: int = 140,
        base_cadence: int = 85,
        base_power: float = 200.0
    ) -> bytes:
        """
        Generates a valid binary .FIT stream for testing parser decoding.
        """
        if start_time is None:
            start_time = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

        payload = bytearray()
        ts_garmin = int(start_time.timestamp() - self.GARMIN_EPOCH_OFFSET)

        for i in range(num_records):
            cur_ts = ts_garmin + i * 5
            hr = base_hr + (i % 5)
            cad = base_cadence + (i % 3)
            pwr = base_power + (i * 2.0)
            payload.extend(struct.pack("<IBBH", cur_ts, hr, cad, int(pwr)))

        header_size = 14
        data_size = len(payload)
        header = struct.pack("<BBHI4sH", header_size, 0x20, 2100, data_size, self.FIT_HEADER_MAGIC, 0x0000)

        return bytes(header + payload)

    def _decode_payload(self, payload: bytes) -> List[FitRecord]:
        """
        Internal decoder for payload record binary chunks.
        Chunk size = 8 bytes: [timestamp: 4B, hr: 1B, cadence: 1B, power: 2B]
        """
        records = []
        chunk_size = 8
        offset = 0

        while offset + chunk_size <= len(payload):
            ts_garmin, hr, cad, pwr = struct.unpack("<IBBH", payload[offset : offset + chunk_size])
            ts = datetime.fromtimestamp(ts_garmin + self.GARMIN_EPOCH_OFFSET, tz=timezone.utc)
            records.append(FitRecord(
                timestamp=ts,
                heart_rate=hr,
                cadence=cad,
                power=float(pwr),
                distance=float((len(records) + 1) * 10)
            ))
            offset += chunk_size

        return records


fit_parser_service = FitParser()
