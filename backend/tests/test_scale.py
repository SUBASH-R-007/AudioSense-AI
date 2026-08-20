"""Tests for camp statistics, multilingual counseling, and the QR handout."""
import io

from fastapi.testclient import TestClient

from app.main import app
from app.services.demo_cases import DEMO_CASES
from app.services.languages import LANGUAGES
from app.services.report import counseling_sheet

client = TestClient(app)

CSV_HEAD = (
    "name,age,sex,occupation,test_date,"
    "r_ac_250,r_ac_500,r_ac_1000,r_ac_2000,r_ac_4000,r_ac_8000,"
    "r_bc_250,r_bc_500,r_bc_1000,r_bc_2000,r_bc_4000,"
    "l_ac_250,l_ac_500,l_ac_1000,l_ac_2000,l_ac_4000,l_ac_8000,"
    "l_bc_250,l_bc_500,l_bc_1000,l_bc_2000,l_bc_4000\n"
)


def row(name, age, notch=False, normal=False):
    if normal:
        ac = [10, 10, 10, 10, 10, 15]
        bc = [5, 5, 5, 5, 5]
    elif notch:
        ac = [15, 15, 20, 25, 60, 30]
        bc = [10, 10, 15, 20, 55]
    else:
        ac = [30, 35, 40, 45, 50, 55]
        bc = [25, 30, 35, 40, 45]
    return (f"{name},{age},male,Factory Worker,2026-01-01,"
            + ",".join(map(str, ac + bc + ac + bc)) + "\n")


def test_camp_summary_reports_prevalence_and_notch_rate():
    csv = CSV_HEAD + row("A", 25, notch=True) + row("B", 35, notch=True) \
        + row("C", 45, notch=True) + row("D", 55) + row("E", 28, normal=True)
    r = client.post("/api/batch",
                    files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")})
    s = r.json()["summary"]
    assert s["total"] == 5
    assert s["impaired"] == 4          # everyone but the normal case
    assert s["impaired_pct"] == 80.0
    assert s["noise_notch"] == 3
    assert s["noise_notch_pct"] == 60.0
    assert "noise notch" in s["headline"]
    assert set(s["by_age_band"]) <= {"0–17", "18–29", "30–44", "45–59", "60+"}
    assert s["by_age_band"]["18–29"]["n"] == 2


def test_camp_summary_headline_falls_back_to_prevalence():
    csv = CSV_HEAD + row("A", 60) + row("B", 62) + row("C", 30, normal=True)
    s = client.post("/api/batch",
                    files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")}
                    ).json()["summary"]
    assert "hearing loss" in s["headline"]


def test_empty_csv_summary_is_safe():
    r = client.post("/api/batch",
                    files={"file": ("c.csv", io.BytesIO(CSV_HEAD.encode()), "text/csv")})
    assert r.json()["summary"]["total"] == 0


# ---------------------------------------------------------- multilingual --

def test_counseling_sheet_covers_every_language():
    analysis = client.post("/api/analyze",
                           json=DEMO_CASES[2]["record"]).json()  # presbycusis
    sheet = counseling_sheet(analysis)
    for lang in LANGUAGES:
        assert lang in sheet, f"missing {lang}"
        assert sheet[lang]["summary"], f"{lang} summary empty"
        assert len(sheet[lang]["tips"]) == 5
        assert sheet[lang]["heading"]
        assert sheet[lang]["native"]


def test_languages_are_actually_distinct_scripts():
    analysis = client.post("/api/analyze", json=DEMO_CASES[2]["record"]).json()
    sheet = counseling_sheet(analysis)
    first_tips = {lang: sheet[lang]["tips"][0] for lang in LANGUAGES}
    assert len(set(first_tips.values())) == len(LANGUAGES)
    # Spot-check that non-Latin scripts really are non-Latin.
    assert any("஀" <= c <= "௿" for c in first_tips["tamil"])
    assert any("ऀ" <= c <= "ॿ" for c in first_tips["hindi"])
    assert any("ఀ" <= c <= "౿" for c in first_tips["telugu"])
    assert any("ಀ" <= c <= "೿" for c in first_tips["kannada"])
    assert any("ഀ" <= c <= "ൿ" for c in first_tips["malayalam"])


def test_urgent_finding_reaches_every_counseling_language():
    record = {
        "patient": {"name": "X", "age": 40, "onset": "sudden"},
        "right": {"ac": {250: 15, 500: 55, 1000: 60, 2000: 65, 4000: 60, 8000: 55},
                  "bc": {250: 12, 500: 52, 1000: 57, 2000: 62, 4000: 57}},
        "left": {"ac": {250: 10, 500: 10, 1000: 10, 2000: 15, 4000: 15, 8000: 20},
                 "bc": {250: 8, 500: 8, 1000: 8, 2000: 12, 4000: 12}},
    }
    analysis = client.post("/api/analyze", json=record).json()
    assert analysis["safety"]["has_urgent"] is True
    sheet = counseling_sheet(analysis)
    for lang in LANGUAGES:
        assert sheet[lang]["summary"], lang
        # The urgent warning must be the first thing the patient reads.
        assert len(sheet[lang]["summary"][0]) > 20


# --------------------------------------------------------------- handout --

def test_handout_qr_and_page_roundtrip():
    analysis = client.post("/api/analyze", json=DEMO_CASES[1]["record"]).json()
    bundle = client.post("/api/report", json=analysis).json()
    r = client.post("/api/handout", json={
        "patient": analysis["patient"], "analysis": analysis,
        "counseling": bundle["counseling"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["hash"] and body["url"].endswith(body["hash"])

    page = client.get(f"/api/handout/{body['hash']}")
    assert page.status_code == 200
    assert "Your Hearing Summary" in page.text
    assert "தமிழ்" in page.text  # language switcher rendered

    qr = client.get("/api/qr", params={"data": body["url"]})
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_handout_returns_404():
    assert client.get("/api/handout/nope123").status_code == 404


def test_oversized_qr_data_is_rejected_not_a_500():
    """/api/qr is public. A hostile string must not reach the encoder.

    The route is on the auth allowlist, so anything it does costs an
    unauthenticated caller nothing. Above ~4,000 characters qrcode raises,
    and that used to escape as a 500 with a traceback in the log.
    """
    assert client.get("/api/qr", params={"data": "A" * 5000}).status_code == 422
    assert client.get("/api/qr", params={"data": ""}).status_code == 422
    # The only string the product itself issues is a handout URL (~100 chars).
    assert client.get("/api/qr", params={"data": "A" * 512}).status_code == 200


def test_one_bad_cell_does_not_abort_the_whole_batch():
    """A camp uploads hundreds of hand-typed rows; one typo must cost one row.

    An out-of-range threshold used to raise inside the row loop and return a
    bare 500 for the entire file, naming neither the row nor the column.
    """
    csv = (CSV_HEAD + row("Good One", 30) + row("Bad One", 31).replace(
        ",30,35,40,45,50,55,", ",30,35,40,45,50,900,", 1) + row("Good Two", 32))
    r = client.post("/api/batch",
                    files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200
    body = r.json()

    assert body["count"] == 2, "both good rows must still be analysed"
    assert body["skipped"] == 1
    assert [e["row"] for e in body["errors"]] == [2]
    assert body["errors"][0]["name"] == "Bad One"
    problem = " ".join(body["errors"][0]["problems"])
    assert "r_ac_8000" in problem, "the offending column must be named"
    assert "900" in problem
    # The bad row must not be silently analysed with a bogus threshold.
    assert all(res["name"] != "Bad One" for res in body["results"])


def test_an_unparseable_cell_is_reported_with_its_column():
    csv = CSV_HEAD + row("Typo", 40).replace(",30,35,", ",30,3o,", 1)
    body = client.post(
        "/api/batch",
        files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    assert body["count"] == 0 and body["skipped"] == 1
    assert "r_ac_500" in " ".join(body["errors"][0]["problems"])


def test_a_clean_batch_reports_no_errors():
    """The error channel must stay empty on good input, or it is just noise."""
    csv = CSV_HEAD + row("A", 30) + row("B", 40, normal=True)
    body = client.post(
        "/api/batch",
        files={"file": ("c.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    assert body["count"] == 2
    assert body["errors"] == [] and body["skipped"] == 0
