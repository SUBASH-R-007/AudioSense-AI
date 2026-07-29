"""Regression test: OpenCV digitizer vs the known ground truth of the
bundled sample photos."""
import json
from pathlib import Path

import pytest

from app.services.vision import digitize_opencv

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

pytestmark = pytest.mark.skipif(
    not (SAMPLES / "ground_truth.json").exists(),
    reason="sample photos not generated — run python -m scripts.make_samples",
)


@pytest.mark.parametrize("name", ["audiogram_photo_1", "audiogram_photo_2"])
def test_digitizer_matches_ground_truth(name):
    truth = json.loads((SAMPLES / "ground_truth.json").read_text())[name]
    image = (SAMPLES / f"{name}.png").read_bytes()
    result = digitize_opencv(image)
    assert result["ok"], result.get("error")

    checked = exact = 0
    for ear in ("right", "left"):
        for conduction in ("ac", "bc"):
            for f, expected in truth[ear][conduction].items():
                got = result[ear][conduction].get(int(f))
                assert got is not None, f"{ear} {conduction} {f} Hz not detected"
                checked += 1
                # Within one 5 dB step of truth.
                assert abs(got - expected) <= 5, (
                    f"{ear} {conduction} {f} Hz: got {got}, expected {expected}"
                )
                if got == expected:
                    exact += 1
    assert checked == 22  # 6 AC + 5 BC per ear
    assert exact / checked >= 0.9  # at least 90% exact
