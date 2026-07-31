"""Tests for OSHA STS and ASHA ototoxicity progression criteria."""
import pytest

from app.clinical.progression import (
    asha_ototoxicity,
    compare_ears,
    ear_deltas,
    osha_sts,
)


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def test_deltas_positive_means_worse():
    deltas = ear_deltas(flat(20), flat(35))
    assert all(d == 15.0 for d in deltas.values())


def test_osha_sts_exactly_10_flags():
    baseline = flat(20)
    current = {**baseline, 2000: 30, 4000: 30}  # +10 at both
    result = osha_sts(ear_deltas(baseline, current))
    assert result["avg_shift"] == 10.0
    assert result["flag"] is True  # criterion is >= 10


def test_osha_sts_below_10_no_flag():
    baseline = flat(20)
    current = {**baseline, 2000: 30, 4000: 25}  # avg 7.5
    result = osha_sts(ear_deltas(baseline, current))
    assert result["avg_shift"] == 7.5
    assert result["flag"] is False


def test_osha_uses_only_2k_4k():
    baseline = flat(20)
    current = {**baseline, 250: 60, 500: 60, 1000: 60}  # low freqs only
    assert osha_sts(ear_deltas(baseline, current))["flag"] is False


def test_asha_20db_single_freq_flags():
    baseline = flat(20)
    current = {**baseline, 4000: 40}  # exactly +20
    result = asha_ototoxicity(ear_deltas(baseline, current))
    assert result["flag"] is True
    assert any("20 dB" in t for t in result["triggers"])


def test_asha_10db_two_adjacent_flags():
    baseline = flat(20)
    current = {**baseline, 2000: 30, 4000: 30}  # +10 adjacent pair
    result = asha_ototoxicity(ear_deltas(baseline, current))
    assert result["flag"] is True
    assert any("adjacent" in t for t in result["triggers"])


def test_asha_10db_two_nonadjacent_no_flag():
    baseline = flat(20)
    current = {**baseline, 500: 30, 4000: 30}  # +10 but not adjacent
    result = asha_ototoxicity(ear_deltas(baseline, current))
    assert result["flag"] is False


def test_asha_nr_at_three_consecutive_flags():
    baseline = flat(60)
    current = {**baseline, 2000: "NR", 4000: "NR", 8000: "NR"}
    result = asha_ototoxicity(
        ear_deltas(baseline, current), baseline, current
    )
    assert any("three consecutive" in t for t in result["triggers"])


def test_compare_ears_bundles_everything():
    result = compare_ears(flat(20), flat(40))
    assert result["osha_sts"]["flag"] is True
    assert result["asha_ototoxicity"]["flag"] is True
    assert result["max_shift"] == 20.0
