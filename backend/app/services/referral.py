"""ENT referral letter — the natural output of the safety engine.

When the battery raises a red flag, the next step is always the same: get
this person in front of an ENT surgeon with the findings that prompted the
referral. This produces that letter in one click, carrying the specific
criteria met rather than a vague "please see and advise".
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

TEAL = colors.HexColor("#0d9488")
SLATE = colors.HexColor("#334155")
ROSE = colors.HexColor("#be123c")

URGENCY_TEXT = {
    "emergency": ("URGENT — SAME-WEEK APPOINTMENT REQUESTED",
                  "This referral concerns a time-critical finding."),
    "urgent": ("PRIORITY REFERRAL", "Early assessment is recommended."),
    "validity": ("ROUTINE — TEST VALIDITY QUERY", "Please note the caveats below."),
    "info": ("ROUTINE REFERRAL", ""),
}


def build_referral_pdf(payload: dict) -> bytes:
    patient = payload.get("patient", {})
    analysis = payload.get("analysis", {})
    safety = analysis.get("safety") or {}
    rules = analysis.get("rules") or {}
    battery = analysis.get("battery") or {}
    alerts = safety.get("alerts", [])
    referrer = payload.get("referrer") or "AudioSense AI screening service"

    level = ("emergency" if safety.get("has_emergency")
             else "urgent" if safety.get("has_urgent")
             else "validity" if safety.get("validity_warning") else "info")
    heading, sub = URGENCY_TEXT[level]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=10, leading=14)
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, textColor=TEAL,
                        alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, textColor=SLATE,
                        spaceBefore=10, spaceAfter=4)
    urgent_style = ParagraphStyle(
        "urgent", parent=body, fontSize=11.5, textColor=ROSE if level in
        ("emergency", "urgent") else SLATE, spaceAfter=6)

    story = [
        Paragraph("Audiology Referral", h1),
        Paragraph(f"To: ENT / Otolaryngology &nbsp;&nbsp;·&nbsp;&nbsp; From: {referrer}"
                  f" &nbsp;&nbsp;·&nbsp;&nbsp; {datetime.now().strftime('%d %b %Y')}", body),
        Spacer(1, 4),
        HRFlowable(width="100%", color=TEAL, thickness=1.2),
        Spacer(1, 8),
        Paragraph(f"<b>{heading}</b>", urgent_style),
    ]
    if sub:
        story.append(Paragraph(sub, body))

    info = [
        ["Patient", patient.get("name", "—"), "Age / Sex",
         f"{patient.get('age', '—')} / {patient.get('sex', '—')}"],
        ["Occupation", patient.get("occupation") or "—", "Test date",
         str(patient.get("test_date") or "—")],
        ["Onset", patient.get("onset", "not recorded"), "Symptoms",
         ", ".join(patient.get("symptoms") or []) or "none recorded"],
    ]
    t = Table(info, colWidths=[24 * mm, 62 * mm, 24 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE),
        ("TEXTCOLOR", (2, 0), (2, -1), SLATE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    story += [Spacer(1, 6), t, Spacer(1, 4)]

    story.append(Paragraph("Reason for referral", h2))
    if alerts:
        for a in alerts:
            if a["level"] == "info":
                continue
            story.append(Paragraph(
                f"<b>{a['title']}</b> ({a['ear'] or 'both'} ear) — {a['detail']} "
                f"<i>{a.get('action', '')}</i>", body))
    else:
        story.append(Paragraph(
            "Routine assessment requested; no red-flag criteria were met on screening.",
            body))

    story.append(Paragraph("Audiometric findings", h2))
    for side in ("right", "left"):
        ear = rules.get(side) or {}
        pta = (ear.get("ac_pta") or {}).get("value")
        grade = (ear.get("who_grade") or {}).get("grade")
        if pta is None:
            continue
        line = (f"<b>{side.capitalize()} ear:</b> PTA {pta:g} dB HL — {grade}, "
                f"{ear.get('type', 'type not determined').lower()}")
        abg = ear.get("abg")
        if abg:
            line += f"; air-bone gap {abg['value']:g} dB"
        story.append(Paragraph(line + ".", body))

    if battery.get("headline"):
        story.append(Paragraph("Test battery", h2))
        story.append(Paragraph(battery["headline"], body))
        for side in ("right", "left"):
            ear_review = battery.get(side) or {}
            for c in ear_review.get("contradictions", []):
                story.append(Paragraph(f"• {side.capitalize()}: {c['title']} — "
                                       f"{c['detail']}", body))
            for c in ear_review.get("confirmations", []):
                story.append(Paragraph(f"• {side.capitalize()}: {c['title']}", body))

    disability = rules.get("disability")
    if disability:
        story.append(Paragraph("Disability assessment", h2))
        story.append(Paragraph(
            f"Binaural hearing disability {disability['binaural_pct']:g}% "
            f"(RPwD Act 2016). {disability['binaural_formula']}", body))

    story += [
        Spacer(1, 10),
        HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")),
        Spacer(1, 6),
        Paragraph("____________________________<br/>Referring clinician "
                  "(signature &amp; registration no.)", body),
        Spacer(1, 6),
        Paragraph("<i>AI-assisted interpretation; final diagnosis requires a "
                  "qualified audiologist. Thresholds were obtained by "
                  "screening audiometry and should be confirmed in a "
                  "calibrated sound booth.</i>",
                  ParagraphStyle("disc", parent=body, fontSize=8.5, textColor=SLATE)),
    ]

    doc.build(story)
    return buf.getvalue()
