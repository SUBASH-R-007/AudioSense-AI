"""Audiogram symbol recognition — the shape decides the ear, not the colour.

The digitizer used to find marks with two HSV masks, so a greyscale chart —
a photocopy, a fax, a scan, a one-pen chart, a thermal printout — produced
"no red/blue audiogram symbols detected" and the feature was simply
unavailable. These tests pin the shape-based replacement: that each of the
eight standard symbols is identified from its geometry alone, that a mark
which is not one of them comes back ``unknown`` rather than forced into a
class, and that a greyscale audiogram now digitizes.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services import symbols as S
from app.services.vision import _detect_grid, digitize_opencv

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


# ------------------------------------------------------------- rendering ---

def render(symbol: str, size: int = 34, thickness: int | None = None) -> np.ndarray:
    """Draw one clinical symbol the way a chart draws it, centred in a box."""
    t = thickness or max(2, size // 14)
    img = np.zeros((size, size), np.uint8)
    c, r = size // 2, int(size * 0.38)
    if symbol == "O":
        cv2.circle(img, (c, c), r, 255, t)
    elif symbol == "X":
        d = int(r * 0.78)
        cv2.line(img, (c - d, c - d), (c + d, c + d), 255, t)
        cv2.line(img, (c - d, c + d), (c + d, c - d), 255, t)
    elif symbol == "triangle":
        cv2.polylines(img, [np.array([[c, c - r], [c - r, c + r], [c + r, c + r]])],
                      True, 255, t)
    elif symbol == "square":
        cv2.rectangle(img, (c - r, c - r), (c + r, c + r), 255, t)
    elif symbol == "[":
        cv2.line(img, (c - r // 2, c - r), (c - r // 2, c + r), 255, t)
        cv2.line(img, (c - r // 2, c - r), (c + r // 2, c - r), 255, t)
        cv2.line(img, (c - r // 2, c + r), (c + r // 2, c + r), 255, t)
    elif symbol == "]":
        cv2.line(img, (c + r // 2, c - r), (c + r // 2, c + r), 255, t)
        cv2.line(img, (c + r // 2, c - r), (c - r // 2, c - r), 255, t)
        cv2.line(img, (c + r // 2, c + r), (c - r // 2, c + r), 255, t)
    elif symbol == "<":
        cv2.line(img, (c + r // 2, c - r), (c - r // 2, c), 255, t)
        cv2.line(img, (c - r // 2, c), (c + r // 2, c + r), 255, t)
    elif symbol == ">":
        cv2.line(img, (c - r // 2, c - r), (c + r // 2, c), 255, t)
        cv2.line(img, (c + r // 2, c), (c - r // 2, c + r), 255, t)
    else:  # pragma: no cover — guards the test itself
        raise AssertionError(f"no renderer for {symbol}")
    return img


def cropped(img: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(img)
    return (img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] > 0).astype(np.uint8)


ALL_SYMBOLS = ["O", "X", "triangle", "square", "[", "]", "<", ">"]


# ------------------------------------------------------------- the table ---

def test_every_symbol_has_a_meaning_and_a_name():
    for label, (ear, conduction, masked) in S.SYMBOL_MEANING.items():
        assert ear in ("right", "left")
        assert conduction in ("ac", "bc")
        assert isinstance(masked, bool)
        assert label in S.SYMBOL_NAME


def test_the_symbol_set_covers_both_ears_masked_and_unmasked():
    """Eight symbols: two ears x two conductions x masked or not."""
    assert len(S.SYMBOL_MEANING) == 8
    assert len(set(S.SYMBOL_MEANING.values())) == 8


def test_bone_symbols_open_toward_the_frequency_line():
    """The geometric regularity the classifier relies on.

    Every right-ear bone symbol opens right; every left-ear one opens left.
    That is what lets the opening direction decide the ear.
    """
    for label in ("[", "<"):
        assert S.SYMBOL_MEANING[label][0] == "right"
    for label in ("]", ">"):
        assert S.SYMBOL_MEANING[label][0] == "left"


# --------------------------------------------------------- classification ---

@pytest.mark.parametrize("symbol", ALL_SYMBOLS)
@pytest.mark.parametrize("size", [20, 28, 40, 56])
def test_each_symbol_is_identified_at_any_size(symbol, size):
    """Scale-free: the same descriptors at 20 px and at 56 px."""
    result = S.classify(cropped(render(symbol, size)))
    assert result["symbol"] == symbol, result["scores"]
    assert result["confidence"] >= S.MIN_SHAPE_CONFIDENCE


@pytest.mark.parametrize("symbol", ALL_SYMBOLS)
def test_each_symbol_survives_the_blur_of_a_phone_photo(symbol):
    img = cv2.GaussianBlur(render(symbol, 40), (5, 5), 0)
    result = S.classify(cropped((img > 70).astype(np.uint8) * 255))
    assert result["symbol"] == symbol, result["scores"]


@pytest.mark.parametrize("symbol,ear", [
    ("O", "right"), ("triangle", "right"), ("<", "right"), ("[", "right"),
    ("X", "left"), ("square", "left"), (">", "left"), ("]", "left"),
])
def test_the_shape_alone_names_the_ear(symbol, ear):
    """No colour anywhere in this test — that is the point of the module."""
    assert S.classify(cropped(render(symbol, 40)))["ear"] == ear


@pytest.mark.parametrize("symbol,conduction", [
    ("O", "ac"), ("X", "ac"), ("triangle", "ac"), ("square", "ac"),
    ("<", "bc"), (">", "bc"), ("[", "bc"), ("]", "bc"),
])
def test_the_shape_names_the_conduction(symbol, conduction):
    assert S.classify(cropped(render(symbol, 40)))["conduction"] == conduction


@pytest.mark.parametrize("symbol,masked", [
    ("O", False), ("X", False), ("<", False), (">", False),
    ("triangle", True), ("square", True), ("[", True), ("]", True),
])
def test_the_shape_says_whether_masking_was_used(symbol, masked):
    assert S.classify(cropped(render(symbol, 40)))["masked"] is masked


def test_a_circle_is_not_read_as_a_square():
    """The corner probe has to be tight enough to miss an inscribed ring.

    A circle comes within 0.146 of each corner of its own bounding box, so a
    probe box sized for the edges catches the ring as well as a square's
    actual corner — and every O was read as a masked LEFT-ear symbol, which
    is the wrong ear and the wrong masking.
    """
    o = S.classify(cropped(render("O", 40)))
    assert o["symbol"] == "O"
    assert o["scores"].get("square", 0) < o["scores"]["O"]


def test_a_mark_that_is_not_a_symbol_is_not_guessed_at():
    """An honest ``unknown`` beats a confident coin flip on a clinical chart."""
    size = 30
    blob = np.zeros((size, size), np.uint8)
    cv2.circle(blob, (15, 15), 10, 255, -1)          # a filled disc
    plus = np.zeros((size, size), np.uint8)
    cv2.line(plus, (15, 4), (15, 26), 255, 3)
    cv2.line(plus, (4, 15), (26, 15), 255, 3)        # a plus, not a cross
    dash = np.zeros((size, size), np.uint8)
    cv2.line(dash, (5, 15), (25, 15), 255, 3)        # a stray line

    for name, img in (("blob", blob), ("plus", plus), ("dash", dash)):
        result = S.classify(cropped(img))
        assert result["symbol"] == "unknown", f"{name} -> {result['symbol']}"
        assert result["ear"] is None
        assert result["reason"]


def test_a_degenerate_mark_is_reported_rather_than_crashing():
    result = S.classify(np.ones((2, 2), np.uint8))
    assert result["symbol"] == "unknown"
    assert result["confidence"] == 0.0


# ------------------------------------------------------- greyscale charts ---

def greyscale_copy(path: Path) -> bytes:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    grey = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return cv2.imencode(".png", grey)[1].tobytes()


@pytest.mark.parametrize("name", ["audiogram_photo_1", "audiogram_photo_2"])
def test_a_greyscale_audiogram_digitizes_at_all(name):
    """The capability this module exists to add.

    The colour-only pipeline returned ``ok: False`` here — not a degraded
    reading, no reading.
    """
    path = SAMPLES / f"{name}.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    result = digitize_opencv(greyscale_copy(path))
    assert result["ok"], result.get("error")
    assert result["detection"]["greyscale"] is True
    assert result["detection"]["colour_used"] is False
    found = sum(len(result[e][c]) for e in ("right", "left") for c in ("ac", "bc"))
    assert found >= 8, f"only {found} thresholds read from a greyscale chart"


@pytest.mark.parametrize("name", ["audiogram_photo_1", "audiogram_photo_2"])
def test_what_a_greyscale_chart_does_yield_is_correct(name):
    """Recall is lower without colour; precision must not be.

    Two ears sharing a threshold draw their symbols at the same point, and on
    a single-colour chart that is a genuine ambiguity — so some values are
    missing. Every value that IS read has to be right.
    """
    path = SAMPLES / f"{name}.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    truth = json.loads((SAMPLES / "ground_truth.json").read_text())[name]
    result = digitize_opencv(greyscale_copy(path))
    assert result["ok"], result.get("error")
    for ear in ("right", "left"):
        for conduction in ("ac", "bc"):
            for freq, expected in truth[ear][conduction].items():
                got = result[ear][conduction].get(int(freq))
                if got is None:
                    continue
                assert abs(got - expected) <= 5, (
                    f"{ear} {conduction} {freq} Hz: read {got}, chart says {expected}")


def test_colour_is_still_used_when_the_chart_has_it():
    """Colour separates two symbols drawn at the same point; shape cannot."""
    path = SAMPLES / "audiogram_photo_1.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    result = digitize_opencv(path.read_bytes())
    assert result["ok"]
    assert result["detection"]["greyscale"] is False
    assert result["detection"]["colour_used"] is True
    # With colour available the reading should be at least as complete as the
    # greyscale one, and in practice much more so.
    colour_found = sum(len(result[e][c])
                       for e in ("right", "left") for c in ("ac", "bc"))
    grey = digitize_opencv(greyscale_copy(path))
    grey_found = sum(len(grey[e][c])
                     for e in ("right", "left") for c in ("ac", "bc"))
    assert colour_found >= grey_found


def test_the_result_says_how_the_ear_was_decided():
    """A reader confirming these values needs to know what decided them."""
    path = SAMPLES / "audiogram_photo_1.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    grey = digitize_opencv(greyscale_copy(path))
    assert "shape alone" in grey["detection"]["note"]
    colour = digitize_opencv(path.read_bytes())
    assert "colour checked against it" in colour["detection"]["note"]


# --------------------------------------------------- physiological sanity ---

def test_bone_conduction_cannot_be_much_poorer_than_air():
    """A chart's printed legend is read as symbols, because it contains them.

    "Right: red O / [" at the foot of a chart is a bracket as far as any
    shape detector is concerned. Read as a bone threshold it produced a
    115 dB bone value against a 55 dB air value — a negative air-bone gap
    that is not a finding but a misreading, and one that would type the ear
    as a profound mixed loss.
    """
    from app.services.vision import NEGATIVE_GAP_TOLERANCE_DB
    assert NEGATIVE_GAP_TOLERANCE_DB >= 10  # the gap significance limit

    path = SAMPLES / "audiogram_photo_1.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    result = digitize_opencv(path.read_bytes())
    for ear in ("right", "left"):
        for freq, bc in result[ear]["bc"].items():
            ac = result[ear]["ac"].get(freq)
            if ac is not None:
                assert bc <= ac + NEGATIVE_GAP_TOLERANCE_DB


def test_the_grid_is_found_before_any_symbol_is_read():
    path = SAMPLES / "audiogram_photo_1.png"
    if not path.exists():
        pytest.skip("sample photos not present")
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    grid = _detect_grid(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    assert grid is not None
    assert sorted(grid["freq_x"]) == [250, 500, 1000, 2000, 4000, 8000]
    marks = S.extract_marks(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), grid)
    assert marks, "no marks extracted from a chart that plainly has them"
    assert all("mask" in m and m["mask"].size for m in marks)
