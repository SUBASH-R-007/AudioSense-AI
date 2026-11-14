"""PDF report: audiogram chart + AI report + QR to the clinical report +
signature line (reportlab).

TWO DOCUMENTS, TWO AUDIENCES, AND THEY DO NOT BELONG IN ONE FILE.

This PDF is the CLINICAL report. It is read by an audiologist, countersigned,
filed, and sent to a referring doctor. The patient counselling sheet is a
different document for a different reader: plain language, in the patient's
own language, written to be read at home and shown to family.

They used to be printed together, which served neither. A clinician filing a
report does not want two pages of counselling in the middle of it; a patient
handed the same file gets their summary wrapped in air-bone gaps and an RPwD
percentage. So the counselling sheet is no longer in the PDF — it is issued on
its own, as the QR handout that puts it on the patient's phone
(``routers/handout.py``), which is where it was always most useful.

The QR on this page opens the CLINICAL report, not the counselling sheet: a
clinician scanning their own printout wants the document they are holding,
readable on a phone and with every number intact.

Tamil text renders with the Windows "Nirmala UI" font when available.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.state_paths import state_dir

# Writable state. Resolved through state_paths so a deployment can move it
# onto a volume that survives a redeploy; unset, this is the original path.
DATA_DIR = state_dir()
VERIFY_STORE = DATA_DIR / "verify_store.json"

#: Sections of the clinical report, in the order they are printed and the
#: order the web view shows them. One list, so the page a QR opens cannot
#: drift out of step with the page it was printed from.
REPORT_SECTIONS = (
    ("Findings", "findings"),
    ("Pattern & Likely Etiologies", "pattern_etiology"),
    ("Degree & Type", "degree_type"),
    ("Disability Assessment (RPwD Act 2016)", "disability"),
    ("Functional Impact", "functional_impact"),
    ("Recommendations", "recommendations"),
)

TEAL = colors.HexColor("#0d9488")
SLATE = colors.HexColor("#334155")

_TAMIL_FONT: str | None = None
for candidate in (r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\NirmalaS.ttf",
                  "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf"):
    if Path(candidate).exists():
        try:
            pdfmetrics.registerFont(TTFont("TamilFont", candidate))
            _TAMIL_FONT = "TamilFont"
            break
        except Exception:
            pass


def result_hash(analysis: dict) -> str:
    canonical = json.dumps(analysis, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def register_hash(h: str, patient_name: str, report: dict | None = None,
                  patient: dict | None = None, engine: str | None = None,
                  verified: bool | None = None) -> None:
    """Record a hash, and the report it belongs to, against that hash.

    The report content is stored so the QR on the printed page can OPEN the
    clinical report rather than merely confirm that a hash is known. What is
    kept is the report's own prose sections and the patient header — not the
    whole analysis payload — so the stored copy is the document, and no more
    of it than the document itself shows.
    """
    store = {}
    if VERIFY_STORE.exists():
        try:
            store = json.loads(VERIFY_STORE.read_text(encoding="utf-8"))
        except Exception:
            store = {}
    entry = {
        "created": datetime.now(timezone.utc).isoformat(),
        "patient": patient_name,
    }
    # Preserve anything an earlier build recorded for this hash: the same
    # analysis regenerated gives the same hash, and a second PDF without a
    # chart or an engine should not blank what the first one stored.
    previous = store.get(h) if isinstance(store.get(h), dict) else {}
    if report is not None:
        entry["report"] = {key: list(report.get(key) or [])
                           for _, key in REPORT_SECTIONS}
        entry["disclaimer"] = report.get("disclaimer", "")
    elif previous.get("report"):
        entry["report"] = previous["report"]
        entry["disclaimer"] = previous.get("disclaimer", "")
    if patient is not None:
        entry["patient_header"] = {
            "name": patient.get("name") or "",
            "age": patient.get("age"),
            "sex": patient.get("sex") or "",
            "test_date": str(patient.get("test_date") or ""),
        }
    elif previous.get("patient_header"):
        entry["patient_header"] = previous["patient_header"]
    if engine is not None:
        entry["engine"] = engine
    if verified is not None:
        entry["verified"] = bool(verified)
    store[h] = entry
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERIFY_STORE.write_text(json.dumps(store, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def lookup_hash(h: str) -> dict | None:
    if VERIFY_STORE.exists():
        try:
            return json.loads(VERIFY_STORE.read_text(encoding="utf-8")).get(h)
        except Exception:
            return None
    return None


def build_pdf(payload: dict, verify_url_base: str = "http://localhost:8000") -> bytes:
    """payload: {patient, analysis, report_bundle, chart_png_b64?}."""
    # `or {}` throughout: these come straight off a client payload, where a
    # key present with an explicit null slips past a `{}` default.
    patient = payload.get("patient") or {}
    analysis = payload.get("analysis") or {}
    bundle = payload.get("report_bundle") or {}
    report = bundle.get("report") or {}
    counseling = bundle.get("counseling") or {}

    h = result_hash(analysis)
    register_hash(h, patient.get("name", ""), report=report, patient=patient,
                  engine=bundle.get("engine"), verified=bundle.get("verified"))
    # The QR opens the CLINICAL report — the document in the reader's hand,
    # readable on a phone. The verification endpoint is still there and is
    # printed below as a URL; it answers a different question ("is this hash
    # one we issued?") and is not what someone scanning a report wants.
    report_url = f"{verify_url_base}/api/report-view/{h}"
    verify_url = f"{verify_url_base}/api/verify/{h}"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm,
                            bottomMargin=14 * mm, leftMargin=16 * mm,
                            rightMargin=16 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=TEAL, fontSize=20,
                        spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=SLATE, fontSize=12,
                        spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    tamil = ParagraphStyle("tamil", parent=body, fontName=_TAMIL_FONT or "Helvetica")

    story = [
        Paragraph("AudioSense AI — Pure Tone Audiometry Report", h1),
        Paragraph(
            f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')} · "
            f"Engine: {bundle.get('engine', 'offline-template')} · "
            + ("Verified ✓" if bundle.get("verified") else "Unverified"),
            ParagraphStyle("meta", parent=body, textColor=SLATE)),
        Spacer(1, 4),
        HRFlowable(width="100%", color=TEAL, thickness=1.2),
        Spacer(1, 6),
    ]

    info = [
        ["Patient", patient.get("name", "—"), "Age / Sex",
         f"{patient.get('age', '—')} / {patient.get('sex', '—')}"],
        ["Occupation", patient.get("occupation") or "—", "Test date",
         str(patient.get("test_date") or "—")],
    ]
    t = Table(info, colWidths=[25 * mm, 65 * mm, 25 * mm, 55 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE),
        ("TEXTCOLOR", (2, 0), (2, -1), SLATE),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    story += [t, Spacer(1, 6)]

    chart_b64 = payload.get("chart_png_b64")
    if chart_b64:
        try:
            img_bytes = base64.b64decode(chart_b64.split(",")[-1])
            img = ImageReader(io.BytesIO(img_bytes))
            iw, ih = img.getSize()
            # Fit within the frame: cap both width and height, keep aspect.
            max_w, max_h = 165 * mm, 150 * mm
            ratio = min(max_w / iw, max_h / ih)
            story += [Image(io.BytesIO(img_bytes), width=iw * ratio,
                            height=ih * ratio), Spacer(1, 4)]
        except Exception:
            story.append(Paragraph("(chart image could not be embedded)", body))

    for title, key in REPORT_SECTIONS:
        lines = report.get(key) or []
        if lines:
            story.append(Paragraph(title, h2))
            for line in lines:
                story.append(Paragraph(f"• {line}", body))

    # NO COUNSELLING SHEET HERE. It is a separate document for a separate
    # reader — see this module's docstring — and it is issued as the QR handout
    # that opens on the patient's own phone, in their own language. Printing it
    # inside the clinical report served neither audience.

    story.append(Paragraph("Verification & Sign-off", h2))
    qr_img = qrcode.make(report_url)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    sig_table = Table(
        [[Image(qr_buf, width=24 * mm, height=24 * mm),
          Paragraph(
              "Scan for this clinical report<br/>"
              f"<font size=8>{report_url}</font><br/>"
              f"Verification hash: <b>{h}</b><br/>"
              f"<font size=8>Check authenticity: {verify_url}</font><br/><br/>"
              "____________________________<br/>Reviewing Audiologist "
              "(signature &amp; seal)", body)]],
        colWidths=[30 * mm, 140 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [sig_table, Spacer(1, 6),
              Paragraph(f"<i>{report.get('disclaimer', '')}</i>",
                        ParagraphStyle("disc", parent=body, textColor=SLATE))]

    doc.build(story)
    return buf.getvalue()
