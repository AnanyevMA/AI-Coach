"""
Physiological Telemetry Analysis Service for AI Adaptive Coach v7.0.

Computes core sports science performance metrics:
- Normalized Power (NP) and Intensity Factor (IF)
- Training Impulse (TRIMP) and Training Stress Score (TSS)
- Exponentially Weighted Moving Average ACWR (Acute:Chronic Workload Ratio)
- HRV z-score: Z_HRV = (ln(rMSSD_7d) - μ_30d) / σ_30d
- 5-Zone distribution for Heart Rate and Power
- Aerobic Decoupling / Heart Rate Drift
- Power Curve analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
import math
import logging
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class NormalizedPowerResult:
    """Normalized Power and Intensity metrics output."""
    normalized_power: float
    intensity_factor: float
    variability_index: float  # NP / Avg Power
    avg_power: float
    max_power: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "normalized_power": self.normalized_power,
            "intensity_factor": self.intensity_factor,
            "variability_index": self.variability_index,
            "avg_power": self.avg_power,
            "max_power": self.max_power,
        }


@dataclass
class ImpulseMetrics:
    """Training load metrics container (TRIMP, TSS, IF)."""
    trimp: float
    tss: float
    intensity_factor: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "trimp": self.trimp,
            "tss": self.tss,
            "intensity_factor": self.intensity_factor,
        }


@dataclass
class ACWRResult:
    """Acute:Chronic Workload Ratio result using EWMA."""
    acute_workload: float  # λ_a = 0.25 (7 days)
    chronic_workload: float  # λ_c = 0.069 (28 days)
    acwr: float
    risk_level: str  # UNDERLOAD, OPTIMAL, CAUTION, HIGH_RISK

    def to_dict(self) -> Dict[str, Union[float, str]]:
        return {
            "acute_workload": self.acute_workload,
            "chronic_workload": self.chronic_workload,
            "acwr": self.acwr,
            "risk_level": self.risk_level,
        }


@dataclass
class HRVZScoreResult:
    """HRV z-score evaluation output."""
    rmssd_7d: float
    ln_rmssd_7d: float
    mean_30d: float
    std_30d: float
    z_score: float
    status: str  # DEPRESSED_FATIGUE, NORMAL, HYPERACTIVE

    def to_dict(self) -> Dict[str, Union[float, str]]:
        return {
            "rmssd_7d": self.rmssd_7d,
            "ln_rmssd_7d": self.ln_rmssd_7d,
            "mean_30d": self.mean_30d,
            "std_30d": self.std_30d,
            "z_score": self.z_score,
            "status": self.status,
        }


@dataclass
class ZoneDistribution:
    """Target metric time distribution across physiological zones."""
    zone: int
    name: str
    min_val: float
    max_val: float
    time_in_zone_seconds: float
    percentage: float

    def to_dict(self) -> Dict[str, Union[int, str, float]]:
        return {
            "zone": self.zone,
            "name": self.name,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "time_in_zone_seconds": self.time_in_zone_seconds,
            "percentage": self.percentage,
        }


@dataclass
class FullTelemetryAnalysis:
    """Comprehensive analysis report for an activity stream."""
    duration_seconds: float
    avg_hr: Optional[float]
    max_hr: Optional[float]
    normalized_power: Optional[float]
    intensity_factor: Optional[float]
    variability_index: Optional[float]
    trimp: Optional[float]
    tss: Optional[float]
    heart_rate_drift_pct: Optional[float]
    hr_zones: List[ZoneDistribution] = field(default_factory=list)
    power_zones: List[ZoneDistribution] = field(default_factory=list)
    power_curve: Dict[int, float] = field(default_factory=dict)


class TelemetryAnalysisService:
    """
    Physiological metrics and telemetry analysis engine for AI Adaptive Coach v7.0.
    """

    LAMBDA_ACUTE = 0.25  # 7-day EWMA decay factor
    LAMBDA_CHRONIC = 0.069  # 28-day EWMA decay factor

    # --------------------------------------------------------------------------
    # 1. Normalized Power (NP) and Intensity Factor (IF)
    # --------------------------------------------------------------------------

    def calculate_normalized_power(
        self,
        power_series: List[float],
        ftp: float = 250.0,
        window_size: int = 30
    ) -> NormalizedPowerResult:
        """
        Calculate Coggan Normalized Power (NP), Intensity Factor (IF), and Variability Index (VI).

        Algorithm:
        1. Calculate 30-second rolling average of power values.
        2. Raise each 30s rolling average to the 4th power.
        3. Take the arithmetic mean of the 4th power values.
        4. Take the 4th root of the mean.
        """
        valid_power = [p for p in power_series if p is not None and not math.isnan(p)]
        if not valid_power:
            return NormalizedPowerResult(
                normalized_power=0.0,
                intensity_factor=0.0,
                variability_index=1.0,
                avg_power=0.0,
                max_power=0.0,
            )

        avg_power = float(sum(valid_power) / len(valid_power))
        max_power = float(max(valid_power))

        if len(valid_power) < window_size:
            np_val = avg_power
        else:
            # 30-second rolling average
            rolling_avg_4th: List[float] = []
            current_sum = sum(valid_power[:window_size])
            rolling_avg_4th.append((current_sum / window_size) ** 4)

            for i in range(window_size, len(valid_power)):
                current_sum += valid_power[i] - valid_power[i - window_size]
                avg_30s = current_sum / window_size
                rolling_avg_4th.append(avg_30s ** 4)

            mean_4th = sum(rolling_avg_4th) / len(rolling_avg_4th)
            np_val = mean_4th ** 0.25

        np_val = round(np_val, 2)
        intensity_factor = round(np_val / ftp, 3) if ftp > 0 else 0.0
        variability_index = round(np_val / avg_power, 3) if avg_power > 0 else 1.0

        return NormalizedPowerResult(
            normalized_power=np_val,
            intensity_factor=intensity_factor,
            variability_index=variability_index,
            avg_power=round(avg_power, 2),
            max_power=round(max_power, 2),
        )

    # --------------------------------------------------------------------------
    # 2. TRIMP (Training Impulse) and TSS (Training Stress Score)
    # --------------------------------------------------------------------------

    def calculate_trimp(
        self,
        hr_series: Optional[List[int]] = None,
        duration_seconds: float = 0.0,
        avg_hr: Optional[float] = None,
        rest_hr: float = 60.0,
        max_hr: float = 190.0,
        is_male: bool = True
    ) -> float:
        """
        Calculate Banister Training Impulse (TRIMP).
        If hr_series is provided, computes continuous instant TRIMP per second.
        Otherwise falls back to total duration and average heart rate.

        Banister formula:
          TRIMP = Duration_minutes * HRr * y
          HRr = (HR - HR_rest) / (HR_max - HR_rest)
          y_male = 0.64 * exp(1.92 * HRr)
          y_female = 0.86 * exp(1.67 * HRr)
        """
        if max_hr <= rest_hr:
            return 0.0

        b = 1.92 if is_male else 1.67
        gender_mult = 0.64 if is_male else 0.86

        if hr_series and len(hr_series) > 0:
            total_trimp = 0.0
            for hr in hr_series:
                if hr is None or hr <= 0:
                    continue
                hrr = (hr - rest_hr) / (max_hr - rest_hr)
                hrr = max(0.0, min(1.0, hrr))
                y = gender_mult * math.exp(b * hrr)
                # 1 second = (1/60) minute
                total_trimp += (1.0 / 60.0) * hrr * y
            return round(total_trimp, 2)

        if duration_seconds > 0 and avg_hr is not None and avg_hr > 0:
            duration_minutes = duration_seconds / 60.0
            hrr = (avg_hr - rest_hr) / (max_hr - rest_hr)
            hrr = max(0.0, min(1.0, hrr))
            y = gender_mult * math.exp(b * hrr)
            trimp = duration_minutes * hrr * y
            return round(trimp, 2)

        return 0.0

    def calculate_tss(
        self,
        duration_seconds: float,
        normalized_power: float,
        ftp: float = 250.0
    ) -> float:
        """
        Calculate Training Stress Score (TSS) using Coggan formula:
        TSS = (sec * NP * IF) / (FTP * 3600) * 100 = (sec * NP^2) / (FTP^2 * 3600) * 100
        """
        if ftp <= 0 or duration_seconds <= 0 or normalized_power <= 0:
            return 0.0

        intensity_factor = normalized_power / ftp
        tss = (duration_seconds * normalized_power * intensity_factor) / (ftp * 3600.0) * 100.0
        return round(tss, 2)

    def calculate_impulse_metrics(
        self,
        duration_seconds: float,
        power_series: Optional[List[float]] = None,
        hr_series: Optional[List[int]] = None,
        ftp: float = 250.0,
        rest_hr: float = 60.0,
        max_hr: float = 190.0,
        is_male: bool = True
    ) -> ImpulseMetrics:
        """
        Compute integrated load impulse metrics (TRIMP, TSS, IF).
        """
        np_res = self.calculate_normalized_power(power_series or [], ftp=ftp) if power_series else None
        np_val = np_res.normalized_power if np_res else 0.0
        if_val = np_res.intensity_factor if np_res else 0.0

        tss = self.calculate_tss(duration_seconds, np_val, ftp=ftp)
        trimp = self.calculate_trimp(
            hr_series=hr_series,
            duration_seconds=duration_seconds,
            rest_hr=rest_hr,
            max_hr=max_hr,
            is_male=is_male
        )

        return ImpulseMetrics(
            trimp=trimp,
            tss=tss,
            intensity_factor=if_val
        )

    # --------------------------------------------------------------------------
    # 3. EWMA Acute:Chronic Workload Ratio (ACWR)
    # --------------------------------------------------------------------------

    def calculate_ewma_acwr(
        self,
        daily_loads: List[float],
        lambda_a: float = LAMBDA_ACUTE,
        lambda_c: float = LAMBDA_CHRONIC,
        initial_acute: Optional[float] = None,
        initial_chronic: Optional[float] = None,
        sport_type: str = "general",
    ) -> ACWRResult:
        """
        Calculate Exponentially Weighted Moving Average (EWMA) ACWR.
        Phase 5.2: Applies sport-specific strain multipliers (Running 1.3x, Strength/Hyrox 1.1x, Cycling/General 1.0x).

        Formulas:
          w_a,t = load_t * λ_a + (1 - λ_a) * w_a,t-1  (Acute: λ_a = 0.25, 7 days)
          w_c,t = load_t * λ_c + (1 - λ_c) * w_c,t-1  (Chronic: λ_c = 0.069, 28 days)
          ACWR = w_a,t / w_c,t
        """
        if not daily_loads:
            return ACWRResult(
                acute_workload=0.0,
                chronic_workload=0.0,
                acwr=1.0,
                risk_level="OPTIMAL"
            )

        # Sport strain multiplier (Phase 5.2)
        sport_multiplier_map = {
            "running": 1.3,
            "marathon": 1.3,
            "strength": 1.1,
            "hyrox": 1.1,
            "cycling": 1.0,
            "swimming": 1.0,
            "general": 1.0,
        }
        multiplier = sport_multiplier_map.get(sport_type.lower(), 1.0)
        adjusted_loads = [load * multiplier for load in daily_loads]

        acute = initial_acute if initial_acute is not None else adjusted_loads[0]
        chronic = initial_chronic if initial_chronic is not None else adjusted_loads[0]

        for load in adjusted_loads:
            acute = load * lambda_a + (1.0 - lambda_a) * acute
            chronic = load * lambda_c + (1.0 - lambda_c) * chronic

        acwr_val = round(acute / chronic, 2) if chronic > 0 else 1.0

        # Risk classification
        if acwr_val < 0.8:
            risk = "UNDERLOAD"
        elif 0.8 <= acwr_val <= 1.3:
            risk = "OPTIMAL"
        elif 1.3 < acwr_val <= 1.5:
            risk = "CAUTION"
        else:
            risk = "HIGH_RISK"

        return ACWRResult(
            acute_workload=round(acute, 2),
            chronic_workload=round(chronic, 2),
            acwr=acwr_val,
            risk_level=risk
        )

    # --------------------------------------------------------------------------
    # 4. HRV Z-Score
    # --------------------------------------------------------------------------

    def calculate_hrv_z_score(
        self,
        rmssd_7d: float,
        mean_30d: float,
        std_30d: float
    ) -> HRVZScoreResult:
        """
        Calculate HRV Z-Score:
          Z_HRV = (ln(rMSSD_7d) - μ_30d) / σ_30d
        Note: μ_30d and σ_30d represent the mean and standard deviation of log-transformed rMSSD
        over the baseline 30-day window.
        """
        if rmssd_7d <= 0:
            raise ValueError("rmssd_7d must be greater than zero.")

        ln_rmssd_7d = math.log(rmssd_7d)

        if std_30d <= 0.00001:
            z_score = 0.0
        else:
            z_score = (ln_rmssd_7d - mean_30d) / std_30d

        z_score = round(z_score, 2)

        if z_score < -1.5:
            status = "DEPRESSED_FATIGUE"
        elif z_score > 1.5:
            status = "HYPERACTIVE"
        else:
            status = "NORMAL"

        return HRVZScoreResult(
            rmssd_7d=round(rmssd_7d, 2),
            ln_rmssd_7d=round(ln_rmssd_7d, 3),
            mean_30d=round(mean_30d, 3),
            std_30d=round(std_30d, 3),
            z_score=z_score,
            status=status
        )

    # --------------------------------------------------------------------------
    # 5. Zone Distributions (5-Zone HR & Power)
    # --------------------------------------------------------------------------

    def calculate_hr_zone_distribution(
        self,
        hr_series: List[int],
        max_hr: int = 190,
        rest_hr: int = 60
    ) -> List[ZoneDistribution]:
        """
        Calculate time spent in 5 heart rate zones (% of max HR).

        Zones:
          Zone 1 (Active Recovery): 50% - 60% max HR
          Zone 2 (Endurance): 60% - 70% max HR
          Zone 3 (Tempo): 70% - 80% max HR
          Zone 4 (Threshold): 80% - 90% max HR
          Zone 5 (Anaerobic / Max): 90% - 100%+ max HR
        """
        valid_hr = [h for h in hr_series if h is not None and h > 0]
        total_seconds = len(valid_hr)

        boundaries = [
            (1, "Zone 1 (Active Recovery)", 0.50 * max_hr, 0.60 * max_hr),
            (2, "Zone 2 (Endurance)", 0.60 * max_hr, 0.70 * max_hr),
            (3, "Zone 3 (Tempo)", 0.70 * max_hr, 0.80 * max_hr),
            (4, "Zone 4 (Threshold)", 0.80 * max_hr, 0.90 * max_hr),
            (5, "Zone 5 (Anaerobic Max)", 0.90 * max_hr, float(max_hr * 1.3)),
        ]

        counts = {z[0]: 0 for z in boundaries}

        for h in valid_hr:
            if h < boundaries[0][2]:
                counts[1] += 1
            elif h >= boundaries[4][2]:
                counts[5] += 1
            else:
                for z_id, name, lower, upper in boundaries:
                    if lower <= h < upper:
                        counts[z_id] += 1
                        break

        result: List[ZoneDistribution] = []
        for z_id, name, lower, upper in boundaries:
            sec = float(counts[z_id])
            pct = round((sec / total_seconds * 100.0), 1) if total_seconds > 0 else 0.0
            result.append(
                ZoneDistribution(
                    zone=z_id,
                    name=name,
                    min_val=round(lower, 1),
                    max_val=round(upper, 1) if upper < 1000 else round(max_hr * 1.1, 1),
                    time_in_zone_seconds=sec,
                    percentage=pct,
                )
            )

        return result

    def calculate_power_zone_distribution(
        self,
        power_series: List[float],
        ftp: float = 250.0
    ) -> List[ZoneDistribution]:
        """
        Calculate time spent in 5 Coggan power zones (% of FTP).

        Zones:
          Zone 1 (Active Recovery): < 55% FTP
          Zone 2 (Endurance): 55% - 75% FTP
          Zone 3 (Tempo): 75% - 90% FTP
          Zone 4 (Lactate Threshold): 90% - 105% FTP
          Zone 5 (Anaerobic / VO2Max): > 105% FTP
        """
        valid_power = [p for p in power_series if p is not None and p >= 0]
        total_seconds = len(valid_power)

        boundaries = [
            (1, "Zone 1 (Active Recovery)", 0.0, 0.55 * ftp),
            (2, "Zone 2 (Endurance)", 0.55 * ftp, 0.75 * ftp),
            (3, "Zone 3 (Tempo)", 0.75 * ftp, 0.90 * ftp),
            (4, "Zone 4 (Threshold)", 0.90 * ftp, 1.05 * ftp),
            (5, "Zone 5 (Anaerobic Capacity)", 1.05 * ftp, float(ftp * 3.0)),
        ]

        counts = {z[0]: 0 for z in boundaries}

        for p in valid_power:
            if p < boundaries[0][3]:
                counts[1] += 1
            elif p >= boundaries[4][2]:
                counts[5] += 1
            else:
                for z_id, name, lower, upper in boundaries:
                    if lower <= p < upper:
                        counts[z_id] += 1
                        break

        result: List[ZoneDistribution] = []
        for z_id, name, lower, upper in boundaries:
            sec = float(counts[z_id])
            pct = round((sec / total_seconds * 100.0), 1) if total_seconds > 0 else 0.0
            result.append(
                ZoneDistribution(
                    zone=z_id,
                    name=name,
                    min_val=round(lower, 1),
                    max_val=round(upper, 1) if upper < 1000 else round(ftp * 1.5, 1),
                    time_in_zone_seconds=sec,
                    percentage=pct,
                )
            )

        return result

    # --------------------------------------------------------------------------
    # 6. Heart Rate Drift & Power Curve Helpers
    # --------------------------------------------------------------------------

    def calculate_heart_rate_drift(
        self,
        hr_series: List[int],
        power_or_speed_series: List[float]
    ) -> Optional[float]:
        """
        Calculate Aerobic Decoupling / Heart Rate Drift percentage.
        Compares Efficiency Factor (EF = Power / HR) between the 1st half and 2nd half.
          Decoupling % = ((EF_half1 - EF_half2) / EF_half1) * 100%
        """
        if len(hr_series) < 60 or len(hr_series) != len(power_or_speed_series):
            return None

        mid = len(hr_series) // 2

        hr1, hr2 = hr_series[:mid], hr_series[mid:]
        p1, p2 = power_or_speed_series[:mid], power_or_speed_series[mid:]

        valid_pairs1 = [(p, h) for p, h in zip(p1, hr1) if p and h and h > 0]
        valid_pairs2 = [(p, h) for p, h in zip(p2, hr2) if p and h and h > 0]

        if not valid_pairs1 or not valid_pairs2:
            return None

        ef1 = (sum(p for p, h in valid_pairs1) / len(valid_pairs1)) / (sum(h for p, h in valid_pairs1) / len(valid_pairs1))
        ef2 = (sum(p for p, h in valid_pairs2) / len(valid_pairs2)) / (sum(h for p, h in valid_pairs2) / len(valid_pairs2))

        if ef1 <= 0:
            return 0.0

        drift_pct = ((ef1 - ef2) / ef1) * 100.0
        return round(drift_pct, 2)

    def calculate_power_curve(
        self,
        power_series: List[float],
        durations: Optional[List[int]] = None
    ) -> Dict[int, float]:
        """
        Calculate Maximal Mean Power (MMP) curve for specified time intervals (in seconds).
        Default intervals: 1s, 5s, 15s, 30s, 60s (1m), 300s (5m), 1200s (20m), 3600s (1h).
        """
        if durations is None:
            durations = [1, 5, 15, 30, 60, 300, 1200, 3600]

        valid_power = [p for p in power_series if p is not None and not math.isnan(p)]
        if not valid_power:
            return {d: 0.0 for d in durations}

        curve: Dict[int, float] = {}

        for d in durations:
            if len(valid_power) < d:
                curve[d] = 0.0
            else:
                curr_sum = sum(valid_power[:d])
                max_avg = curr_sum / d

                for i in range(d, len(valid_power)):
                    curr_sum += valid_power[i] - valid_power[i - d]
                    avg_d = curr_sum / d
                    if avg_d > max_avg:
                        max_avg = avg_d

                curve[d] = round(max_avg, 1)

        return curve

    def analyze_full_activity(
        self,
        hr_series: Optional[List[int]] = None,
        power_series: Optional[List[float]] = None,
        ftp: float = 250.0,
        max_hr: int = 190,
        rest_hr: int = 60,
        is_male: bool = True
    ) -> FullTelemetryAnalysis:
        """
        Perform complete multi-metric telemetry analysis for activity streams.
        """
        duration = max(len(hr_series or []), len(power_series or []))
        if duration == 0:
            return FullTelemetryAnalysis(
                duration_seconds=0.0,
                avg_hr=None,
                max_hr=None,
                normalized_power=None,
                intensity_factor=None,
                variability_index=None,
                trimp=None,
                tss=None,
                heart_rate_drift_pct=None,
            )

        hrs = [h for h in (hr_series or []) if h is not None and h > 0]
        avg_hr = round(sum(hrs) / len(hrs), 1) if hrs else None
        max_hr_val = float(max(hrs)) if hrs else None

        np_res = self.calculate_normalized_power(power_series or [], ftp=ftp) if power_series else None
        trimp = self.calculate_trimp(hr_series=hr_series, duration_seconds=float(duration), rest_hr=rest_hr, max_hr=max_hr, is_male=is_male)
        tss = self.calculate_tss(float(duration), np_res.normalized_power, ftp=ftp) if np_res else None

        hr_zones = self.calculate_hr_zone_distribution(hr_series or [], max_hr=max_hr, rest_hr=rest_hr) if hr_series else []
        power_zones = self.calculate_power_zone_distribution(power_series or [], ftp=ftp) if power_series else []
        power_curve = self.calculate_power_curve(power_series or []) if power_series else {}

        hr_drift = None
        if hr_series and power_series and len(hr_series) == len(power_series):
            hr_drift = self.calculate_heart_rate_drift(hr_series, power_series)

        return FullTelemetryAnalysis(
            duration_seconds=float(duration),
            avg_hr=avg_hr,
            max_hr=max_hr_val,
            normalized_power=np_res.normalized_power if np_res else None,
            intensity_factor=np_res.intensity_factor if np_res else None,
            variability_index=np_res.variability_index if np_res else None,
            trimp=trimp,
            tss=tss,
            heart_rate_drift_pct=hr_drift,
            hr_zones=hr_zones,
            power_zones=power_zones,
            power_curve=power_curve,
        )

    def downsample_telemetry_series(self, series: List[float], window_size: int = 10) -> List[float]:
        """
        Downsamples high-frequency time series (e.g. 1Hz telemetry data)
        into averaged window intervals to optimize LLM context size and reduce token burn by up to 80%.
        """
        if not series or window_size <= 1:
            return series or []
        
        downsampled = []
        for i in range(0, len(series), window_size):
            chunk = series[i : i + window_size]
            if chunk:
                avg_val = round(sum(chunk) / len(chunk), 1)
                downsampled.append(avg_val)
        return downsampled

    def calculate_fueling_and_hydration(
        self,
        duration_seconds: float,
        avg_hr: Optional[float] = None,
        max_hr: float = 190.0,
        intensity_factor: float = 0.75,
    ) -> Dict[str, float]:
        """
        Phase 5.2: Calculates glycogen carbohydrate burn (g/hour), fluid loss (ml/hour),
        and sodium requirement (mg) based on workout duration and intensity factor.
        """
        hours = duration_seconds / 3600.0
        if hours <= 0:
            return {"carbs_grams": 0.0, "fluid_ml": 0.0, "sodium_mg": 0.0}

        # Carbs burn rate: ~30g/h for Z2 (IF ~0.65), up to 90g/h for Z4+ (IF > 0.85)
        carb_rate_g_per_hr = max(20.0, min(90.0, intensity_factor * 85.0))
        total_carbs_g = round(carb_rate_g_per_hr * hours, 1)

        # Sweat rate: ~500ml/h baseline, up to 1200ml/h under high intensity
        sweat_rate_ml_per_hr = max(500.0, min(1200.0, 500.0 + intensity_factor * 600.0))
        total_fluid_ml = round(sweat_rate_ml_per_hr * hours, 0)

        # Sodium loss: ~500mg per liter of sweat
        total_sodium_mg = round((total_fluid_ml / 1000.0) * 500.0, 0)

        return {
            "carbs_grams": total_carbs_g,
            "fluid_ml": total_fluid_ml,
            "sodium_mg": total_sodium_mg,
        }


telemetry_analysis_service = TelemetryAnalysisService()


