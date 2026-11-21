"""Scanned audiometry REPORT -> thresholds plus the printed result fields.

``vision.py`` reads a photograph of a chart. This reads the document a clinic
actually hands over: one page with a letterhead, the patient's details, the
audiogram somewhere in the middle, and the printed results underneath. The
tests here cover locating the chart on such a page, the field parser, and the
honesty rules — that a field which could not be read comes back absent rather
than blank, and that a value which is read is right.

The page is drawn here with OpenCV rather than shipped as a fixture: the test
needs to know the ground truth exactly, and a generated page keeps the chart
geometry explicit instead of hidden in a PNG.
"""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import report_scan as R

client = TestClient(app)

AC_FREQS = [250, 500, 1000, 2000, 4000, 8000]
BC_FREQS = [250, 500, 1000, 2000, 4000]

RIGHT = {"ac": {250: 20, 500: 25, 1000: 35, 2000: 50, 4000: 65, 8000: 75},
         "bc": {250: 15, 500: 20, 1000: 30, 2000: 45, 4000: 60}}
LEFT = {"ac": {250: 55, 500: 60, 1000: 70, 2000: 85, 4000: 95, 8000: 100},
        "bc": {250: 50, 500: 55, 1000: 65, 2000: 80, 4000: 90}}

INK = (40, 40, 40)
RED = (30, 30, 200)
BLUE = (200, 60, 30)


def report_page(colour: bool = True, with_text: bool = True) -> np.ndarray:
    """An A4-shaped report: letterhead, details, audiogram, printed results."""
    w, h = 1240, 1754
    page = np.full((h, w, 3), 255, np.uint8)

    # chart box, a third of the page down
    x0, x1 = 170, 1070
    y0, y1 = 520, 1180
    cols = {f: int(x0 + (x1 - x0) * i / 5) for i, f in enumerate(AC_FREQS)}

    def y_of(db):
        return int(y0 + (y1 - y0) * (db - (-10)) / (120 - (-10)))

    for db in range(-10, 121, 10):
        cv2.line(page, (x0, y_of(db)), (x1, y_of(db)), (140, 140, 140), 1)
    for f in AC_FREQS:
        cv2.line(page, (cols[f], y0), (cols[f], y1), (140, 140, 140), 1)

    r_colour = RED if colour else INK
    l_colour = BLUE if colour else INK
    for f, db in RIGHT["ac"].items():
        cv2.circle(page, (cols[f], y_of(db)), 13, r_colour, 3)
    for f, db in LEFT["ac"].items():
        c, y, d = cols[f], y_of(db), 10
        cv2.line(page, (c - d, y - d), (c + d, y + d), l_colour, 3)
        cv2.line(page, (c - d, y + d), (c + d, y - d), l_colour, 3)
    for f, db in RIGHT["bc"].items():
        c, y, d = cols[f] - 34, y_of(db), 13
        cv2.line(page, (c - 5, y - d), (c - 5, y + d), r_colour, 3)
        cv2.line(page, (c - 5, y - d), (c + 6, y - d), r_colour, 3)
        cv2.line(page, (c - 5, y + d), (c + 6, y + d), r_colour, 3)
    for f, db in LEFT["bc"].items():
        c, y, d = cols[f] + 34, y_of(db), 13
        cv2.line(page, (c + 5, y - d), (c + 5, y + d), l_colour, 3)
        cv2.line(page, (c + 5, y - d), (c - 6, y - d), l_colour, 3)
        cv2.line(page, (c + 5, y + d), (c - 6, y + d), l_colour, 3)

    if with_text:
        font = cv2.FONT_HERSHEY_SIMPLEX
        put = lambda t, x, y, s=0.62: cv2.putText(  # noqa: E731
            page, t, (x, y), font, s, INK, 2, cv2.LINE_AA)
        put("CITY ENT AND AUDIOLOGY CENTRE", 230, 90, 0.9)
        put("PURE TONE AUDIOMETRY REPORT", 330, 150, 0.7)
        put("Patient Name : Meena Raghavan", 120, 300)
        put("Date of Test : 14/11/2026", 700, 300)
        put("Age : 58", 120, 360)
        put("Sex : Female", 700, 360)
        put("RESULTS", 120, 1290, 0.7)
        put("Right PTA : 43.8 dB HL", 120, 1360)
        put("Left PTA : 77.5 dB HL", 700, 1360)
        put("Right SRT : 45 dB HL", 120, 1420)
        put("Left SRT : 80 dB HL", 700, 1420)
        put("Right SDS : 88 %", 120, 1480)
        put("Left SDS : 52 %", 700, 1480)
        put("IMPRESSION : Asymmetric mixed hearing loss", 120, 1560)
        put("RECOMMENDATION : MRI and ENT review", 120, 1620)
    return page


def encoded(page: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", page)
    assert ok
    return buf.tobytes()


# ------------------------------------------------------- locating the chart ---

def test_the_chart_is_found_on_a_page_of_other_content():
    chart = R.locate_chart(report_page())
    assert chart is not None
    # It must be the audiogram, not the whole sheet and not a text block.
    assert 0.1 < chart["area_fraction"] < 0.8
    assert chart["gridlines"]["vertical"] >= 4
    assert chart["gridlines"]["horizontal"] >= 6


def test_the_chart_box_contains_the_whole_plot():
    """Clipping the top gridline rescales the entire dB axis.

    The crop is handed to the digitizer, which maps the topmost gridline it
    finds to -10 dB. Lose that line and every threshold on the page comes
    out shifted by a constant — and looking perfectly plausible.
    """
    page = report_page()
    chart = R.locate_chart(page)
    # The drawn plot box is y 520..1180, x 170..1070.
    assert chart["y"] <= 520
    assert chart["y"] + chart["h"] >= 1180
    assert chart["x"] <= 170
    assert chart["x"] + chart["w"] >= 1070


def test_a_page_with_no_chart_is_reported_not_invented():
    page = np.full((900, 700, 3), 255, np.uint8)
    cv2.putText(page, "No audiogram here", (60, 400), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, INK, 2)
    assert R.locate_chart(page) is None

    result = R.scan(encoded(page), allow_llm=False)
    assert result["ok"] is True
    assert result["chart"] is None
    assert result["thresholds"] is None
    assert any("No audiogram chart was found" in n for n in result["notes"])


def test_a_bordered_table_is_not_mistaken_for_an_audiogram():
    """A few crossing rules are not a plot: an audiogram has many rows."""
    page = np.full((1200, 900, 3), 255, np.uint8)
    for i in range(4):
        y = 300 + i * 90
        cv2.line(page, (100, y), (800, y), (120, 120, 120), 2)
    for i in range(3):
        x = 100 + i * 350
        cv2.line(page, (x, 300), (x, 570), (120, 120, 120), 2)
    assert R.locate_chart(page) is None


# ------------------------------------------------------ reading the chart ---

@pytest.mark.parametrize("colour", [True, False])
def test_the_audiogram_on_a_report_page_is_read(colour):
    result = R.scan(encoded(report_page(colour=colour)), allow_llm=False)
    assert result["ok"]
    assert result["chart"] is not None
    thresholds = result["thresholds"]
    assert thresholds and thresholds["ok"], (thresholds or {}).get("error")
    found = sum(len(thresholds[e][c])
                for e in ("right", "left") for c in ("ac", "bc"))
    assert found >= 6, f"only {found} thresholds read off the report page"


@pytest.mark.parametrize("colour", [True, False])
def test_every_threshold_read_off_a_report_page_is_correct(colour):
    """Recall may be partial; precision must not be.

    A transcription tool that reads nine values correctly and leaves the
    tenth blank is useful. One that reads ten and gets one wrong is not,
    because nothing on screen says which.
    """
    result = R.scan(encoded(report_page(colour=colour)), allow_llm=False)
    thresholds = result["thresholds"]
    assert thresholds and thresholds["ok"]
    truth = {"right": RIGHT, "left": LEFT}
    for ear in ("right", "left"):
        for conduction in ("ac", "bc"):
            for freq, expected in truth[ear][conduction].items():
                got = thresholds[ear][conduction].get(freq)
                if got is None:
                    continue
                assert abs(got - expected) <= 5, (
                    f"{ear} {conduction} {freq} Hz: read {got}, page says {expected}")


# ------------------------------------------------------------ the fields ---

def test_fields_are_parsed_from_their_printed_labels():
    text = """
    CITY ENT AND AUDIOLOGY CENTRE
    Patient Name : Meena Raghavan
    Age : 58          Sex : Female
    Date of Test : 14/11/2026
    Right PTA : 43.8 dB HL
    Left PTA : 77.5 dB HL
    Right SRT : 45 dB HL
    Left SDS : 52 %
    IMPRESSION : Asymmetric mixed hearing loss
    RECOMMENDATION : MRI and ENT review
    """
    fields = R.parse_fields(text)
    assert fields["name"]["value"] == "Meena Raghavan"
    assert fields["age"]["value"] == 58
    assert fields["sex"]["value"] == "female"
    assert fields["test_date"]["value"] == "14/11/2026"
    assert fields["right_pta"]["value"] == 43.8
    assert fields["left_pta"]["value"] == 77.5
    assert fields["right_srt"]["value"] == 45
    assert fields["left_wrs"]["value"] == 52
    assert "mixed" in fields["impression"]["value"].lower()
    assert "MRI" in fields["recommendation"]["value"]


def test_the_longest_matching_label_wins():
    """"Right PTA" must not be captured by the bare "pta" label."""
    fields = R.parse_fields("Right PTA : 30\nLeft PTA : 60")
    assert fields["right_pta"]["value"] == 30
    assert fields["left_pta"]["value"] == 60


def test_a_field_that_is_not_a_value_is_dropped_rather_than_coerced():
    fields = R.parse_fields("Right PTA : see chart\nAge : not recorded")
    assert "right_pta" not in fields
    assert "age" not in fields


def test_an_out_of_range_value_is_refused():
    """A misread digit must not become a threshold."""
    assert "age" not in R.parse_fields("Age : 580")
    assert "right_pta" not in R.parse_fields("Right PTA : 400 dB HL")
    assert "left_wrs" not in R.parse_fields("Left SDS : 180 %")


def test_nothing_is_parsed_out_of_an_empty_page():
    assert R.parse_fields("") == {}
    assert R.parse_fields("   \n  \n") == {}


def test_every_expected_field_is_declared_for_the_ui():
    """The UI shows unread fields as boxes to fill, so it needs the full list."""
    result = R.scan(encoded(report_page()), allow_llm=False)
    keys = {f["key"] for f in result["expected_fields"]}
    assert keys == set(R.FIELD_PATTERNS)
    for field in result["expected_fields"]:
        assert field["label"] and field["kind"]


def test_text_regions_are_found_outside_the_chart():
    """These are the crops a clinician reads the fields off in guided mode."""
    page = report_page()
    chart = R.locate_chart(page)
    regions = R.text_regions(page, chart)
    assert regions, "no text blocks found on a page full of text"
    # None of them may overlap the chart: its axis labels are not report fields.
    for r in regions:
        centre_y = r["y"] + r["h"] / 2
        centre_x = r["x"] + r["w"] / 2
        inside = (chart["x"] <= centre_x <= chart["x"] + chart["w"]
                  and chart["y"] <= centre_y <= chart["y"] + chart["h"])
        assert not inside, f"region {r} sits inside the chart"


# ------------------------------------------------------------ capability ---

def test_ocr_availability_is_reported_with_a_reason():
    available, why = R.ocr_available()
    assert isinstance(available, bool)
    assert why
    if not available:
        # The message has to say the chart still works, or a reader concludes
        # the whole upload failed.
        assert "audiogram" in why.lower()


def test_the_capability_endpoint_sets_expectations_before_an_upload():
    body = client.get("/api/digitize/report/capability").json()
    assert body["chart"] is True
    assert "ocr" in body and "llm_vision" in body
    assert body["fields_automatic"] == bool(body["ocr"] or body["llm_vision"])
    assert body["note"]


def test_guided_mode_is_flagged_when_the_fields_must_be_typed():
    result = R.scan(encoded(report_page()), allow_llm=False)
    assert result["guided"] is (result["method"] == "none")
    if result["guided"]:
        assert result["fields"] == {}
        assert result["text_regions"]
    assert "suggestion" in result["human_in_the_loop"]


# ------------------------------------------------------------- endpoints ---

def test_report_endpoint_reads_a_page():
    res = client.post("/api/digitize/report",
                      files={"file": ("report.png", encoded(report_page()),
                                      "image/png")})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"]
    assert body["chart"]
    assert body["thresholds"]["ok"]


def test_report_endpoint_refuses_an_empty_upload():
    res = client.post("/api/digitize/report",
                      files={"file": ("empty.png", b"", "image/png")})
    assert res.status_code == 400


def test_report_endpoint_refuses_something_that_is_not_an_image():
    res = client.post("/api/digitize/report",
                      files={"file": ("notes.txt", b"not an image at all",
                                      "text/plain")})
    assert res.status_code == 400


def test_the_chart_endpoint_is_untouched_by_the_report_one():
    """Two documents, two paths: a photo of a chart needs no page analysis."""
    res = client.post("/api/digitize",
                      files={"file": ("chart.png",
                                      encoded(report_page(with_text=False)),
                                      "image/png")})
    assert res.status_code == 200
    assert res.json().get("ok") is True
