"""Tests for the 5-year progression forecast."""
import pytest

from app.clinical.forecast import forecast, forecast_ear


def flat(level, freqs=(250, 500, 1000, 2000, 4000, 8000)):
    return {f: level for f in freqs}


def test_stable_hearing_projects_flat_under_exposure():
    f = forecast_ear(flat(20), flat(20), interval_years=3.0, age=40)
    assert f["mean_slope"] == 0.0
    assert f["exposed_pta"][-1]["pta"] == 20.0


def test_worsening_projects_forward_linearly():
    # +15 dB over 3 years = 5 dB/year -> +25 dB at year 5
    f = forecast_ear(flat(20), flat(35), interval_years=3.0, age=40)
    assert f["mean_slope"] == pytest.approx(5.0, abs=0.01)
    assert f["exposed_pta"][-1]["pta"] == pytest.approx(60.0, abs=0.1)


def test_protected_scenario_is_better_than_exposed():
    f = forecast_ear(flat(20), flat(40), interval_years=2.0, age=45)
    assert f["protected_pta"][-1]["pta"] < f["exposed_pta"][-1]["pta"]
    assert f["preventable_db"] > 0


def test_grade_change_detected():
    # Normal now, projected into loss
    f = forecast_ear(flat(10), flat(18), interval_years=2.0, age=40)
    assert f["current_grade"] == "Normal hearing"
    assert f["grade_change"] is True


def test_uncertainty_band_widens_with_time():
    f = forecast_ear(flat(20), flat(35), interval_years=3.0, age=40)
    band = f["uncertainty_band"]
    width0 = band[0]["high"] - band[0]["low"]
    width5 = band[-1]["high"] - band[-1]["low"]
    assert width5 > width0


def test_years_to_disability_floor():
    # PTA 15 now, +5 dB/year -> crosses 25 dB in 2 years
    f = forecast_ear(flat(10), flat(15), interval_years=1.0, age=40)
    assert f["years_to_disability_floor"] == pytest.approx(2.0, abs=0.1)


def test_no_forecast_for_short_interval():
    assert forecast_ear(flat(20), flat(30), interval_years=0.2, age=40) is None


def test_full_forecast_requires_valid_dates():
    both = {"right": flat(20), "left": flat(20)}
    assert forecast(both, both, None, None)["available"] is False
    assert forecast(both, both, "2026-01-01", "2026-02-01")["available"] is False


def test_full_forecast_bundles_both_ears_and_disability():
    baseline = {"right": flat(20), "left": flat(20)}
    current = {"right": flat(40), "left": flat(40)}
    f = forecast(baseline, current, "2023-01-01", "2026-01-01", age=45)
    assert f["available"] is True
    assert f["interval_years"] == pytest.approx(3.0, abs=0.02)
    assert f["right"] and f["left"]
    assert f["disability_projected"]["binaural_pct"] > f["disability_now"]["binaural_pct"]
