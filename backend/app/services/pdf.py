"""PDF report: audiogram chart + AI report + counseling sheet + QR
verification hash + signature line (reportlab).

Tamil text renders with the Windows "Nirmala UI" font when available;
otherwise the Tamil section is replaced by a note (Helvetica lacks Tamil
glyphs).
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

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
VERIFY_STORE = DATA_DIR / "verify_store.json"

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


def register_hash(h: str, patient_name: str) -> None:
    store = {}
    if VERIFY_STORE.exists():
        try:
            store = json.loads(VERIFY_STORE.read_text(encoding="utf-8"))
        except Exception:
            store = {}
    store[h] = {
        "created": datetime.now(timezone.utc).isoformat(),
        "patient": patient_name,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VERIFY_STORE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def lookup_hash(h: str) -> dict | None:
    if VERIFY_STORE.exists():
        try:
            return json.loads(VERIFY_STORE.read_text(encoding="utf-8")).get(h)
        except Exception:
            return None
    return None


def build_pdf(payload: dict, verify_url_base: str = "http://localhost:8000") -> bytes:
    """payload: {patient, analysis, report_bundle, chart_png_b64?}."""
    patient = payload.get("patient", {})
    analysis = payload.get("analysis", {})
    bundle = payload.get("report_bundle", {})
    report = bundle.get("report", {})
    counseling = bundle.get("counseling", {})

    h = result_hash(analysis)
    register_hash(h, patient.get("name", ""))
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

    sections = [
        ("Findings", "findings"), ("Pattern & Likely Etiologies", "pattern_etiology"),
        ("Degree & Type", "degree_type"), ("Disability Assessment (RPwD Act 2016)", "disability"),
        ("Functional Impact", "functional_impact"), ("Recommendations", "recommendations"),
    ]
    for title, key in sections:
        lines = report.get(key) or []
        if lines:
            story.append(Paragraph(title, h2))
            for line in lines:
                story.append(Paragraph(f"• {line}", body))

    en = counseling.get("english", {})
    ta = counseling.get("tamil", {})
    if en:
        story.append(Paragraph("Patient Counseling (English)", h2))
        for s in en.get("summary", []) + en.get("tips", []):
            story.append(Paragraph(f"• {s}", body))
    if ta:
        story.append(Paragraph("Patient Counseling (Tamil / தமிழ்)"
                               if _TAMIL_FONT else "Patient Counseling (Tamil)",
                               ParagraphStyle("h2t", parent=h2,
                                              fontName=_TAMIL_FONT or "Helvetica-Bold")))
        if _TAMIL_FONT:
            for s in ta.get("summary", []) + ta.get("tips", []):
                story.append(Paragraph(f"• {s}", tamil))
        else:
            story.append(Paragraph(
                "(Tamil font not available on this system — see the web app "
                "for the Tamil counseling sheet)", body))

    story.append(Paragraph("Verification & Sign-off", h2))
    qr_img = qrcode.make(verify_url)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    sig_table = Table(
        [[Image(qr_buf, width=24 * mm, height=24 * mm),
          Paragraph(
              f"Verification hash: <b>{h}</b><br/>{verify_url}<br/><br/>"
              "____________________________<br/>Reviewing Audiologist "
              "(signature &amp; seal)", body)]],
        colWidths=[30 * mm, 140 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [sig_table, Spacer(1, 6),
              Paragraph(f"<i>{report.get('disclaimer', '')}</i>",
                        ParagraphStyle("disc", parent=body, textColor=SLATE))]

    doc.build(story)
    return buf.getvalue()
