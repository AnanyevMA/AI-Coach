"""
FIT, GPX, and TCX Telemetry File Parser Service for AI Adaptive Coach v7.0.

Provides robust parsing for binary .FIT files, GPX XML, and TCX XML telemetry data.
Extracts time-series data for heart rate, cadence, power, speed, GPS altitude,
and lap intervals. Includes fallback simulator mode when fitparse library is missing
or synthetic telemetry generation is required.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import io
import math
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

# Optional dependency fitparse for FIT binary decoding
try:
    import fitparse  # type: ignore
    HAS_FITPARSE = True
except ImportError:
    fitparse = None
    HAS_FITPARSE = False

logger = logging.getLogger(__name__)


@dataclass
class TelemetryPoint:
    """Individual time-series telemetry record."""
    timestamp: datetime
    heart_rate: Optional[int] = None
    cadence: Optional[int] = None
    power: Optional[float] = None
    speed: Optional[float] = None  # meters per second
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None  # meters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "heart_rate": self.heart_rate,
            "cadence": self.cadence,
            "power": self.power,
            "speed": self.speed,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
        }


@dataclass
class LapData:
    """Summary metrics for individual lap or split segment."""
    lap_index: int
    start_time: datetime
    duration_seconds: float
    distance_meters: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_power: Optional[float] = None
    max_power: Optional[float] = None
    avg_speed: Optional[float] = None  # m/s
    max_speed: Optional[float] = None  # m/s
    total_elevation_gain: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lap_index": self.lap_index,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "avg_power": self.avg_power,
            "max_power": self.max_power,
            "avg_speed": self.avg_speed,
            "max_speed": self.max_speed,
            "total_elevation_gain": self.total_elevation_gain,
        }


@dataclass
class ParsedActivity:
    """Comprehensive parsed activity data container."""
    activity_type: str  # running, cycling, swimming, generic
    start_time: datetime
    duration_seconds: float
    distance_meters: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_power: Optional[float] = None
    max_power: Optional[float] = None
    avg_speed: Optional[float] = None
    max_speed: Optional[float] = None
    total_elevation_gain: Optional[float] = None
    records: List[TelemetryPoint] = field(default_factory=list)
    laps: List[LapData] = field(default_factory=list)
    is_simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_type": self.activity_type,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "avg_power": self.avg_power,
            "max_power": self.max_power,
            "avg_speed": self.avg_speed,
            "max_speed": self.max_speed,
            "total_elevation_gain": self.total_elevation_gain,
            "records_count": len(self.records),
            "laps_count": len(self.laps),
            "is_simulated": self.is_simulated,
        }


class FITParserService:
    """
    Telemetry file parser for FIT, GPX, and TCX files.
    Includes automated fallback simulation when fitparse is unavailable
    or binary format cannot be parsed natively.
    """

    SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)

    def parse_file(
        self,
        file_path: Union[str, Path],
        file_format: Optional[str] = None
    ) -> ParsedActivity:
        """
        Parse file from filesystem path. Automatically infers format if not provided.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {file_path}")

        if not file_format:
            ext = path.suffix.lower().lstrip(".")
            file_format = ext if ext in ["fit", "gpx", "tcx"] else "fit"

        with open(path, "rb") as f:
            content = f.read()

        return self.parse_bytes(content, file_format=file_format)

    def parse_bytes(
        self,
        content: bytes,
        file_format: str = "fit"
    ) -> ParsedActivity:
        """
        Parse telemetry binary or XML content bytes according to specified format.
        """
        fmt = file_format.lower().strip()
        if fmt == "fit":
            return self.parse_fit_bytes(content)
        elif fmt == "gpx":
            return self.parse_gpx_bytes(content)
        elif fmt == "tcx":
            return self.parse_tcx_bytes(content)
        else:
            raise ValueError(f"Unsupported telemetry format: '{file_format}'. Expected 'fit', 'gpx', or 'tcx'.")

    def parse_fit_bytes(self, content: bytes) -> ParsedActivity:
        """
        Parse binary .FIT content using fitparse if available.
        Falls back to simulator mode if fitparse is absent or parsing raises an exception.
        """
        if not HAS_FITPARSE:
            logger.info("fitparse library not installed. Falling back to FIT simulation parser.")
            return self.generate_simulated_activity(
                activity_type="running",
                duration_seconds=1800,
                start_time=datetime.now(timezone.utc)
            )

        try:
            fit_file = fitparse.FitFile(io.BytesIO(content))
            fit_file.parse()

            records: List[TelemetryPoint] = []
            laps: List[LapData] = []
            activity_type = "generic"
            start_time: Optional[datetime] = None
            total_duration = 0.0
            total_distance = 0.0
            session_avg_hr: Optional[int] = None
            session_max_hr: Optional[int] = None
            session_avg_power: Optional[float] = None
            session_max_power: Optional[float] = None
            session_avg_speed: Optional[float] = None
            session_max_speed: Optional[float] = None
            session_elevation_gain: Optional[float] = None

            # Extract session data if present
            for session in fit_file.get_messages("session"):
                vals = session.get_values()
                if "sport" in vals and vals["sport"]:
                    activity_type = str(vals["sport"]).lower()
                if "start_time" in vals and vals["start_time"]:
                    start_time = self._ensure_utc(vals["start_time"])
                if "total_elapsed_time" in vals and vals["total_elapsed_time"]:
                    total_duration = float(vals["total_elapsed_time"])
                if "total_distance" in vals and vals["total_distance"]:
                    total_distance = float(vals["total_distance"])
                if "avg_heart_rate" in vals and vals["avg_heart_rate"]:
                    session_avg_hr = int(vals["avg_heart_rate"])
                if "max_heart_rate" in vals and vals["max_heart_rate"]:
                    session_max_hr = int(vals["max_heart_rate"])
                if "avg_power" in vals and vals["avg_power"]:
                    session_avg_power = float(vals["avg_power"])
                if "max_power" in vals and vals["max_power"]:
                    session_max_power = float(vals["max_power"])
                if "avg_speed" in vals and vals["avg_speed"]:
                    session_avg_speed = float(vals["avg_speed"])
                if "max_speed" in vals and vals["max_speed"]:
                    session_max_speed = float(vals["max_speed"])
                if "total_ascent" in vals and vals["total_ascent"]:
                    session_elevation_gain = float(vals["total_ascent"])

            # Extract record messages
            for record in fit_file.get_messages("record"):
                vals = record.get_values()
                rec_ts = vals.get("timestamp")
                if not rec_ts:
                    continue

                ts = self._ensure_utc(rec_ts)
                if start_time is None:
                    start_time = ts

                hr = int(vals["heart_rate"]) if "heart_rate" in vals and vals["heart_rate"] is not None else None
                cad = int(vals["cadence"]) if "cadence" in vals and vals["cadence"] is not None else None
                pwr = float(vals["power"]) if "power" in vals and vals["power"] is not None else None
                spd = float(vals.get("enhanced_speed") or vals.get("speed") or 0.0) or None
                alt = float(vals.get("enhanced_altitude") or vals.get("altitude") or 0.0) or None

                lat_raw = vals.get("position_lat")
                lon_raw = vals.get("position_long")
                lat = self._convert_semicircle(lat_raw) if lat_raw is not None else None
                lon = self._convert_semicircle(lon_raw) if lon_raw is not None else None

                records.append(
                    TelemetryPoint(
                        timestamp=ts,
                        heart_rate=hr,
                        cadence=cad,
                        power=pwr,
                        speed=spd,
                        latitude=lat,
                        longitude=lon,
                        altitude=alt,
                    )
                )

            # Extract lap messages
            lap_idx = 1
            for lap in fit_file.get_messages("lap"):
                vals = lap.get_values()
                lap_start = self._ensure_utc(vals.get("start_time") or start_time or datetime.now(timezone.utc))
                lap_dur = float(vals.get("total_elapsed_time") or vals.get("total_timer_time") or 0.0)
                lap_dist = float(vals["total_distance"]) if "total_distance" in vals and vals["total_distance"] is not None else None
                lap_avg_hr = int(vals["avg_heart_rate"]) if "avg_heart_rate" in vals and vals["avg_heart_rate"] is not None else None
                lap_max_hr = int(vals["max_heart_rate"]) if "max_heart_rate" in vals and vals["max_heart_rate"] is not None else None
                lap_avg_pwr = float(vals["avg_power"]) if "avg_power" in vals and vals["avg_power"] is not None else None
                lap_max_pwr = float(vals["max_power"]) if "max_power" in vals and vals["max_power"] is not None else None
                lap_avg_spd = float(vals["avg_speed"]) if "avg_speed" in vals and vals["avg_speed"] is not None else None
                lap_max_spd = float(vals["max_speed"]) if "max_speed" in vals and vals["max_speed"] is not None else None
                lap_ascent = float(vals["total_ascent"]) if "total_ascent" in vals and vals["total_ascent"] is not None else None

                laps.append(
                    LapData(
                        lap_index=lap_idx,
                        start_time=lap_start,
                        duration_seconds=lap_dur,
                        distance_meters=lap_dist,
                        avg_hr=lap_avg_hr,
                        max_hr=lap_max_hr,
                        avg_power=lap_avg_pwr,
                        max_power=lap_max_pwr,
                        avg_speed=lap_avg_spd,
                        max_speed=lap_max_spd,
                        total_elevation_gain=lap_ascent,
                    )
                )
                lap_idx += 1

            if not records and not laps:
                logger.warning("FIT file parsed but contained no records or laps. Generating simulated fallback.")
                return self.generate_simulated_activity()

            if start_time is None:
                start_time = records[0].timestamp if records else datetime.now(timezone.utc)

            if total_duration == 0.0 and len(records) > 1:
                total_duration = (records[-1].timestamp - records[0].timestamp).total_seconds()

            # Aggregate stats from records if session stats are missing
            activity = self._finalize_activity_stats(
                activity_type=activity_type,
                start_time=start_time,
                duration_seconds=total_duration,
                distance_meters=total_distance,
                avg_hr=session_avg_hr,
                max_hr=session_max_hr,
                avg_power=session_avg_power,
                max_power=session_max_power,
                avg_speed=session_avg_speed,
                max_speed=session_max_speed,
                total_elevation_gain=session_elevation_gain,
                records=records,
                laps=laps,
                is_simulated=False,
            )
            return activity

        except Exception as e:
            logger.warning(f"Error parsing .FIT binary data ({str(e)}). Falling back to simulation mode.")
            return self.generate_simulated_activity(
                activity_type="running",
                duration_seconds=1800,
                start_time=datetime.now(timezone.utc)
            )

    def parse_gpx_bytes(self, content: Union[bytes, str]) -> ParsedActivity:
        """
        Parse GPX XML data into structured ParsedActivity format.
        """
        if isinstance(content, str):
            xml_str = content
        else:
            xml_str = content.decode("utf-8", errors="replace")

        root = ET.fromstring(xml_str)
        records: List[TelemetryPoint] = []
        laps: List[LapData] = []
        activity_type = "running"
        start_time: Optional[datetime] = None

        # Check track type if specified
        for trk_type in root.iter():
            if self._local_tag(trk_type) == "type" and trk_type.text:
                activity_type = trk_type.text.lower()
                break

        prev_pt: Optional[TelemetryPoint] = None
        current_distance = 0.0

        for trkpt in root.iter():
            if self._local_tag(trkpt) != "trkpt":
                continue

            lat_attr = trkpt.attrib.get("lat")
            lon_attr = trkpt.attrib.get("lon")
            lat = float(lat_attr) if lat_attr else None
            lon = float(lon_attr) if lon_attr else None

            ts: Optional[datetime] = None
            ele: Optional[float] = None
            hr: Optional[int] = None
            cad: Optional[int] = None
            pwr: Optional[float] = None
            spd: Optional[float] = None

            for child in trkpt:
                tag = self._local_tag(child)
                if tag == "time" and child.text:
                    ts = self._parse_iso_time(child.text)
                elif tag == "ele" and child.text:
                    ele = float(child.text)
                elif tag == "speed" and child.text:
                    spd = float(child.text)
                elif tag == "extensions":
                    # Parse extensions (Garmin GPX extensions)
                    for ext_elem in child.iter():
                        ext_tag = self._local_tag(ext_elem)
                        if ext_tag == "hr" and ext_elem.text:
                            hr = int(float(ext_elem.text))
                        elif ext_tag == "cad" and ext_elem.text:
                            cad = int(float(ext_elem.text))
                        elif ext_tag in ["power", "watts"] and ext_elem.text:
                            pwr = float(ext_elem.text)
                        elif ext_tag == "speed" and ext_elem.text:
                            spd = float(ext_elem.text)

            if ts is None:
                continue

            if start_time is None:
                start_time = ts

            # Compute speed from distance if missing
            if spd is None and prev_pt and prev_pt.latitude is not None and prev_pt.longitude is not None and lat is not None and lon is not None:
                dist_step = self._haversine_distance(prev_pt.latitude, prev_pt.longitude, lat, lon)
                dt = (ts - prev_pt.timestamp).total_seconds()
                if dt > 0:
                    spd = dist_step / dt
                    current_distance += dist_step

            pt = TelemetryPoint(
                timestamp=ts,
                heart_rate=hr,
                cadence=cad,
                power=pwr,
                speed=spd,
                latitude=lat,
                longitude=lon,
                altitude=ele,
            )
            records.append(pt)
            prev_pt = pt

        if not records:
            logger.warning("GPX file parsed but contained no valid trackpoints.")
            return self.generate_simulated_activity()

        if start_time is None:
            start_time = records[0].timestamp

        duration_seconds = (records[-1].timestamp - records[0].timestamp).total_seconds()
        laps = self._partition_into_laps(records)

        return self._finalize_activity_stats(
            activity_type=activity_type,
            start_time=start_time,
            duration_seconds=duration_seconds,
            distance_meters=current_distance if current_distance > 0 else None,
            avg_hr=None,
            max_hr=None,
            avg_power=None,
            max_power=None,
            avg_speed=None,
            max_speed=None,
            total_elevation_gain=None,
            records=records,
            laps=laps,
            is_simulated=False,
        )

    def parse_tcx_bytes(self, content: Union[bytes, str]) -> ParsedActivity:
        """
        Parse TCX XML data into structured ParsedActivity format.
        """
        if isinstance(content, str):
            xml_str = content
        else:
            xml_str = content.decode("utf-8", errors="replace")

        root = ET.fromstring(xml_str)
        records: List[TelemetryPoint] = []
        laps: List[LapData] = []
        activity_type = "running"
        start_time: Optional[datetime] = None

        # Extract sport type from Activity tag
        for elem in root.iter():
            if self._local_tag(elem) == "Activity":
                sport = elem.attrib.get("Sport")
                if sport:
                    activity_type = sport.lower()
                break

        lap_idx = 1
        for lap_elem in root.iter():
            if self._local_tag(lap_elem) != "Lap":
                continue

            lap_start_str = lap_elem.attrib.get("StartTime")
            lap_start = self._parse_iso_time(lap_start_str) if lap_start_str else datetime.now(timezone.utc)
            if start_time is None:
                start_time = lap_start

            lap_dur = 0.0
            lap_dist = None
            lap_avg_hr = None
            lap_max_hr = None
            lap_max_spd = None

            for child in lap_elem:
                c_tag = self._local_tag(child)
                if c_tag == "TotalTimeSeconds" and child.text:
                    lap_dur = float(child.text)
                elif c_tag == "DistanceMeters" and child.text:
                    lap_dist = float(child.text)
                elif c_tag == "MaximumSpeed" and child.text:
                    lap_max_spd = float(child.text)
                elif c_tag == "AverageHeartRateBpm":
                    v_elem = self._find_descendant_by_tag(child, "Value")
                    if v_elem is not None and v_elem.text:
                        lap_avg_hr = int(float(v_elem.text))
                elif c_tag == "MaximumHeartRateBpm":
                    v_elem = self._find_descendant_by_tag(child, "Value")
                    if v_elem is not None and v_elem.text:
                        lap_max_hr = int(float(v_elem.text))

            # Extract Trackpoints in this lap
            lap_records: List[TelemetryPoint] = []
            for tp in lap_elem.iter():
                if self._local_tag(tp) != "Trackpoint":
                    continue

                ts: Optional[datetime] = None
                lat: Optional[float] = None
                lon: Optional[float] = None
                alt: Optional[float] = None
                hr: Optional[int] = None
                cad: Optional[int] = None
                pwr: Optional[float] = None
                spd: Optional[float] = None

                for sub in tp:
                    s_tag = self._local_tag(sub)
                    if s_tag == "Time" and sub.text:
                        ts = self._parse_iso_time(sub.text)
                    elif s_tag == "AltitudeMeters" and sub.text:
                        alt = float(sub.text)
                    elif s_tag == "Cadence" and sub.text:
                        cad = int(float(sub.text))
                    elif s_tag == "HeartRateBpm":
                        v = self._find_descendant_by_tag(sub, "Value")
                        if v is not None and v.text:
                            hr = int(float(v.text))
                    elif s_tag == "Position":
                        lat_e = self._find_child_by_tag(sub, "LatitudeDegrees")
                        lon_e = self._find_child_by_tag(sub, "LongitudeDegrees")
                        if lat_e is not None and lat_e.text:
                            lat = float(lat_e.text)
                        if lon_e is not None and lon_e.text:
                            lon = float(lon_e.text)
                    elif s_tag == "Extensions":
                        for ext in sub.iter():
                            e_tag = self._local_tag(ext)
                            if e_tag in ["Watts", "Power"] and ext.text:
                                pwr = float(ext.text)
                            elif e_tag in ["Speed"] and ext.text:
                                spd = float(ext.text)

                if ts is not None:
                    point = TelemetryPoint(
                        timestamp=ts,
                        heart_rate=hr,
                        cadence=cad,
                        power=pwr,
                        speed=spd,
                        latitude=lat,
                        longitude=lon,
                        altitude=alt,
                    )
                    records.append(point)
                    lap_records.append(point)

            laps.append(
                LapData(
                    lap_index=lap_idx,
                    start_time=lap_start,
                    duration_seconds=lap_dur,
                    distance_meters=lap_dist,
                    avg_hr=lap_avg_hr,
                    max_hr=lap_max_hr,
                    avg_power=None,
                    max_power=None,
                    avg_speed=None,
                    max_speed=lap_max_spd,
                    total_elevation_gain=None,
                )
            )
            lap_idx += 1

        if not records:
            logger.warning("TCX file parsed but contained no trackpoints.")
            return self.generate_simulated_activity()

        if start_time is None:
            start_time = records[0].timestamp

        total_duration = (records[-1].timestamp - records[0].timestamp).total_seconds()
        return self._finalize_activity_stats(
            activity_type=activity_type,
            start_time=start_time,
            duration_seconds=total_duration,
            distance_meters=None,
            avg_hr=None,
            max_hr=None,
            avg_power=None,
            max_power=None,
            avg_speed=None,
            max_speed=None,
            total_elevation_gain=None,
            records=records,
            laps=laps,
            is_simulated=False,
        )

    def generate_simulated_activity(
        self,
        activity_type: str = "running",
        duration_seconds: int = 1800,
        start_time: Optional[datetime] = None
    ) -> ParsedActivity:
        """
        Generate realistic simulated telemetry dataset with 1Hz records, laps,
        heart rate drift, cadence, power, elevation gain, and speed.
        """
        if start_time is None:
            start_time = datetime.now(timezone.utc)
        elif start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        records: List[TelemetryPoint] = []
        is_cycling = activity_type.lower() in ["cycling", "biking", "ride"]

        base_hr = 120.0
        target_hr = 158.0 if not is_cycling else 145.0
        base_cad = 88 if is_cycling else 172
        base_pwr = 230.0 if is_cycling else 260.0
        base_speed = 8.5 if is_cycling else 3.2  # m/s

        current_alt = 120.0
        total_elevation_gain = 0.0

        for t in range(duration_seconds):
            ts = start_time + timedelta(seconds=t)

            # HR warmup curve (first 300s), steady state + slight drift
            if t < 300:
                hr_val = base_hr + (target_hr - base_hr) * (t / 300.0)
            else:
                drift = (t - 300) * 0.003  # cardiac drift ~5 bpm per hour
                hr_val = target_hr + drift + (math.sin(t / 15.0) * 2.0)

            # Cadence, Power, Speed variation
            cad_val = base_cad + int(math.sin(t / 10.0) * 3)
            pwr_val = base_pwr + (math.sin(t / 20.0) * 25.0)
            spd_val = base_speed + (math.sin(t / 30.0) * 0.4)

            # Sinusoidal hill profile for altitude
            alt_delta = math.cos(t / 50.0) * 0.15
            current_alt += alt_delta
            if alt_delta > 0:
                total_elevation_gain += alt_delta

            records.append(
                TelemetryPoint(
                    timestamp=ts,
                    heart_rate=int(round(hr_val)),
                    cadence=cad_val,
                    power=round(pwr_val, 1),
                    speed=round(spd_val, 2),
                    latitude=55.7558 + (t * 0.00001),
                    longitude=37.6173 + (t * 0.00001),
                    altitude=round(current_alt, 1),
                )
            )

        laps = self._partition_into_laps(records, lap_duration_seconds=300)

        return self._finalize_activity_stats(
            activity_type=activity_type,
            start_time=start_time,
            duration_seconds=float(duration_seconds),
            distance_meters=None,
            avg_hr=None,
            max_hr=None,
            avg_power=None,
            max_power=None,
            avg_speed=None,
            max_speed=None,
            total_elevation_gain=total_elevation_gain,
            records=records,
            laps=laps,
            is_simulated=True,
        )

    # --------------------------------------------------------------------------
    # Private Helper Methods
    # --------------------------------------------------------------------------

    def _convert_semicircle(self, val: Any) -> Optional[float]:
        if val is None:
            return None
        v = float(val)
        if abs(v) > 180.0:
            return v * self.SEMICIRCLE_TO_DEG
        return v

    def _local_tag(self, elem: ET.Element) -> str:
        return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    def _find_child_by_tag(self, elem: ET.Element, target_tag: str) -> Optional[ET.Element]:
        for child in elem:
            if self._local_tag(child) == target_tag:
                return child
        return None

    def _find_descendant_by_tag(self, elem: ET.Element, target_tag: str) -> Optional[ET.Element]:
        for child in elem.iter():
            if self._local_tag(child) == target_tag:
                return child
        return None

    def _parse_iso_time(self, text: str) -> datetime:
        t_str = text.strip()
        if t_str.endswith("Z"):
            t_str = t_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(t_str)
        return self._ensure_utc(dt)

    def _ensure_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lam = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def _partition_into_laps(
        self,
        records: List[TelemetryPoint],
        lap_duration_seconds: int = 300
    ) -> List[LapData]:
        if not records:
            return []

        laps: List[LapData] = []
        lap_idx = 1
        curr_chunk: List[TelemetryPoint] = []
        chunk_start_time = records[0].timestamp

        for rec in records:
            curr_chunk.append(rec)
            elapsed = (rec.timestamp - chunk_start_time).total_seconds()

            if elapsed >= lap_duration_seconds:
                lap = self._build_lap_from_chunk(lap_idx, curr_chunk)
                laps.append(lap)
                lap_idx += 1
                curr_chunk = []
                chunk_start_time = rec.timestamp

        if curr_chunk:
            lap = self._build_lap_from_chunk(lap_idx, curr_chunk)
            laps.append(lap)

        return laps

    def _build_lap_from_chunk(self, lap_index: int, chunk: List[TelemetryPoint]) -> LapData:
        start_time = chunk[0].timestamp
        duration = (chunk[-1].timestamp - chunk[0].timestamp).total_seconds()
        if duration == 0 and len(chunk) > 1:
            duration = float(len(chunk))

        hrs = [r.heart_rate for r in chunk if r.heart_rate is not None]
        pwrs = [r.power for r in chunk if r.power is not None]
        spds = [r.speed for r in chunk if r.speed is not None]

        avg_hr = int(round(sum(hrs) / len(hrs))) if hrs else None
        max_hr = max(hrs) if hrs else None
        avg_power = round(sum(pwrs) / len(pwrs), 1) if pwrs else None
        max_power = max(pwrs) if pwrs else None
        avg_speed = round(sum(spds) / len(spds), 2) if spds else None
        max_speed = max(spds) if spds else None

        # Distance calculation
        dist = 0.0
        for i in range(1, len(chunk)):
            p1, p2 = chunk[i - 1], chunk[i]
            if p1.latitude and p1.longitude and p2.latitude and p2.longitude:
                dist += self._haversine_distance(p1.latitude, p1.longitude, p2.latitude, p2.longitude)
            elif p2.speed:
                dt = (p2.timestamp - p1.timestamp).total_seconds()
                dist += p2.speed * dt

        # Elevation gain
        ascent = 0.0
        for i in range(1, len(chunk)):
            if chunk[i].altitude and chunk[i - 1].altitude:
                diff = chunk[i].altitude - chunk[i - 1].altitude
                if diff > 0:
                    ascent += diff

        return LapData(
            lap_index=lap_index,
            start_time=start_time,
            duration_seconds=duration,
            distance_meters=round(dist, 1) if dist > 0 else None,
            avg_hr=avg_hr,
            max_hr=max_hr,
            avg_power=avg_power,
            max_power=max_power,
            avg_speed=avg_speed,
            max_speed=max_speed,
            total_elevation_gain=round(ascent, 1) if ascent > 0 else None,
        )

    def _finalize_activity_stats(
        self,
        activity_type: str,
        start_time: datetime,
        duration_seconds: float,
        distance_meters: Optional[float],
        avg_hr: Optional[int],
        max_hr: Optional[int],
        avg_power: Optional[float],
        max_power: Optional[float],
        avg_speed: Optional[float],
        max_speed: Optional[float],
        total_elevation_gain: Optional[float],
        records: List[TelemetryPoint],
        laps: List[LapData],
        is_simulated: bool,
    ) -> ParsedActivity:
        hrs = [r.heart_rate for r in records if r.heart_rate is not None]
        pwrs = [r.power for r in records if r.power is not None]
        spds = [r.speed for r in records if r.speed is not None]

        final_avg_hr = avg_hr if avg_hr is not None else (int(round(sum(hrs) / len(hrs))) if hrs else None)
        final_max_hr = max_hr if max_hr is not None else (max(hrs) if hrs else None)

        final_avg_pwr = avg_power if avg_power is not None else (round(sum(pwrs) / len(pwrs), 1) if pwrs else None)
        final_max_pwr = max_power if max_power is not None else (max(pwrs) if pwrs else None)

        final_avg_spd = avg_speed if avg_speed is not None else (round(sum(spds) / len(spds), 2) if spds else None)
        final_max_spd = max_speed if max_speed is not None else (max(spds) if spds else None)

        if distance_meters is None or distance_meters == 0.0:
            calc_dist = 0.0
            for i in range(1, len(records)):
                p1, p2 = records[i - 1], records[i]
                if p1.latitude and p1.longitude and p2.latitude and p2.longitude:
                    calc_dist += self._haversine_distance(p1.latitude, p1.longitude, p2.latitude, p2.longitude)
                elif p2.speed:
                    dt = (p2.timestamp - p1.timestamp).total_seconds()
                    calc_dist += p2.speed * dt
            distance_meters = round(calc_dist, 1) if calc_dist > 0 else None

        if total_elevation_gain is None or total_elevation_gain == 0.0:
            ascent = 0.0
            for i in range(1, len(records)):
                if records[i].altitude and records[i - 1].altitude:
                    diff = records[i].altitude - records[i - 1].altitude
                    if diff > 0:
                        ascent += diff
            total_elevation_gain = round(ascent, 1) if ascent > 0 else None

        return ParsedActivity(
            activity_type=activity_type,
            start_time=start_time,
            duration_seconds=duration_seconds,
            distance_meters=distance_meters,
            avg_hr=final_avg_hr,
            max_hr=final_max_hr,
            avg_power=final_avg_pwr,
            max_power=final_max_pwr,
            avg_speed=final_avg_spd,
            max_speed=final_max_spd,
            total_elevation_gain=total_elevation_gain,
            records=records,
            laps=laps,
            is_simulated=is_simulated,
        )


fit_parser_service = FITParserService()
