"""Pydantic data models for AudioSense AI.

A patient test consists of demographics plus, per ear, air-conduction (AC)
and bone-conduction (BC) thresholds in dB HL at the standard audiometric
frequencies. AC is tested at 250-8000 Hz; BC is conventionally tested only
up to 4000 Hz (vibrator output limits).

Threshold values are integers in dB HL (-10..120, 5 dB steps by convention),
the string "NR" (No Response at audiometer limits), or null (not tested).
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

AC_FREQS: List[int] = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS: List[int] = [250, 500, 1000, 2000, 4000]
PTA_FREQS: List[int] = [500, 1000, 2000, 4000]

#: dB HL value substituted for "No Response" in computations (audiometer max).
NR_DB: int = 120

ThresholdValue = Union[int, Literal["NR"]]


class SpeechPoint(BaseModel):
    """One word-recognition measurement: score (%) at a presentation level."""

    level: int
    score: float = Field(ge=0, le=100)


class OAEPoint(BaseModel):
    """One DPOAE measurement: emission and noise floor at a frequency."""

    freq: int
    amplitude: float   # dB SPL
    noise_floor: float  # dB SPL


class EarData(BaseModel):
    """The full test battery for one ear."""

    ac: Dict[int, Optional[ThresholdValue]] = Field(default_factory=dict)
    bc: Dict[int, Optional[ThresholdValue]] = Field(default_factory=dict)
    #: Speech Reception Threshold, dB HL (lowest level for 50% spondee repetition).
    srt: Optional[int] = None
    #: Word recognition scores at one or more presentation levels.
    wrs: List[SpeechPoint] = Field(default_factory=list)
    #: Whether masking was applied when these thresholds were obtained.
    masked: bool = False

    # --- immittance -------------------------------------------------------
    #: Tympanometric peak pressure, daPa.
    tymp_pressure: Optional[float] = None
    #: Static admittance / compliance, mmho.
    tymp_compliance: Optional[float] = None
    #: Equivalent ear-canal volume, cm3.
    tymp_ecv: Optional[float] = None
    #: Acoustic reflex thresholds, dB HL. A key present with value None
    #: means "absent at maximum output"; an empty dict means "not tested".
    reflexes: Dict[str, Optional[float]] = Field(default_factory=dict)

    # --- otoacoustic emissions -------------------------------------------
    oae: List[OAEPoint] = Field(default_factory=list)

    # --- aided verification ----------------------------------------------
    #: Aided (functional gain) thresholds measured in the sound field.
    aided: Dict[int, Optional[ThresholdValue]] = Field(default_factory=dict)

    @field_validator("ac", "bc")
    @classmethod
    def _validate_thresholds(cls, v: Dict[int, Optional[ThresholdValue]]):
        for freq, val in v.items():
            if freq not in AC_FREQS:
                raise ValueError(f"unsupported frequency {freq} Hz")
            if isinstance(val, int) and not (-10 <= val <= 120):
                raise ValueError(f"threshold {val} dB at {freq} Hz outside -10..120")
        return v


class PatientInfo(BaseModel):
    name: str = "Anonymous"
    age: int = Field(ge=0, le=120, default=40)
    sex: str = "unspecified"
    occupation: str = ""
    test_date: Optional[date] = None
    #: "gradual" | "sudden" | "unknown" — sudden onset changes urgency entirely.
    onset: str = "unknown"
    #: Reported symptoms, e.g. ["tinnitus", "vertigo", "aural fullness"].
    symptoms: List[str] = Field(default_factory=list)


class TestRecord(BaseModel):
    """One complete pure-tone audiometry test."""

    patient: PatientInfo = Field(default_factory=PatientInfo)
    right: EarData = Field(default_factory=EarData)
    left: EarData = Field(default_factory=EarData)


class ProgressionRequest(BaseModel):
    baseline: TestRecord
    current: TestRecord


def effective_db(value: Optional[ThresholdValue]) -> Optional[float]:
    """Numeric dB HL for a threshold: NR -> NR_DB (120), untested -> None."""
    if value is None:
        return None
    if value == "NR":
        return float(NR_DB)
    return float(value)


def ear_to_numeric(thresholds: Dict[int, Optional[ThresholdValue]]) -> Dict[int, Optional[float]]:
    return {int(f): effective_db(v) for f, v in thresholds.items()}
