"""PDF download, the clinical report the QR opens, and QR verification."""
from __future__ import annotations

import html

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, Response

from app.services import pdf

router = APIRouter(prefix="/api")


@router.post("/pdf")
def make_pdf(request: Request, payload: dict = Body(...)):
    base = str(request.base_url).rstrip("/")
    pdf_bytes = pdf.build_pdf(payload, verify_url_base=base)
    name = ((payload.get("patient") or {}).get("name") or "report").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="AudioSense_{name}.pdf"'},
    )


@router.get("/report-view/{h}", response_class=HTMLResponse)
def view_report(h: str):
    """The clinical report, readable on a phone — what the QR on the PDF opens.

    THIS IS THE CLINICAL DOCUMENT, not the patient counselling sheet. The
    counselling sheet has its own QR and its own route
    (``routers/handout.py``); mixing them is what this change undoes.

    The path is a capability URL, reachable without signing in, and that is a
    deliberate trade-off rather than an oversight: the person scanning the
    code is holding the printout and is using a phone that has no session.
    It follows the model the counselling handout already uses — a 16-hex
    character hash, which is 64 bits of unguessable — and it carries the same
    limitation, recorded in SCALING.md gap 4: these links do not expire. Only
    the report's own prose and patient header are stored, so the link exposes
    the document and nothing beyond it.
    """
    entry = pdf.lookup_hash(h)
    if not entry or not entry.get("report"):
        return HTMLResponse(
            "<h1>Report not found</h1><p>This link was not issued by this "
            "AudioSense AI instance, or the report was generated before "
            "scannable reports were available.</p>", status_code=404)

    head = entry.get("patient_header") or {}
    rows = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd></div>"
        for label, value in (
            ("Patient", head.get("name") or "—"),
            ("Age / Sex", f"{head.get('age', '—')} / {head.get('sex') or '—'}"),
            ("Test date", head.get("test_date") or "—"),
        ))

    sections = []
    for title, key in pdf.REPORT_SECTIONS:
        lines = (entry["report"] or {}).get(key) or []
        if not lines:
            continue
        items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
        sections.append(
            f"<section><h2>{html.escape(title)}</h2><ul>{items}</ul></section>")

    verified = entry.get("verified")
    badge = ("<span class='ok'>Verified ✓</span>" if verified
             else "<span class='warn'>Unverified</span>" if verified is False
             else "")

    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinical Report — AudioSense AI</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0;
         background: #f8fafc; color: #0f172a; line-height: 1.6; }}
  header {{ background: #134e4a; color: #fff; padding: 18px 20px; }}
  header h1 {{ margin: 0; font-size: 17px; }}
  header p {{ margin: 4px 0 0; font-size: 12.5px; opacity: .85; }}
  .ok {{ background: #10b981; border-radius: 999px; padding: 2px 9px;
        font-size: 11px; font-weight: 700; }}
  .warn {{ background: #f59e0b; border-radius: 999px; padding: 2px 9px;
          font-size: 11px; font-weight: 700; }}
  main {{ padding: 16px; max-width: 680px; margin: 0 auto; }}
  dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0 0 14px;
       background: #fff; border-radius: 12px; padding: 14px; }}
  dl div {{ min-width: 0; }}
  dt {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em;
       color: #64748b; }}
  dd {{ margin: 2px 0 0; font-size: 14.5px; font-weight: 600; }}
  section {{ background: #fff; border-radius: 12px; padding: 16px;
             margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.05); }}
  h2 {{ font-size: 13px; margin: 0 0 8px; color: #0f766e;
        text-transform: uppercase; letter-spacing: .05em; }}
  ul {{ padding-left: 20px; margin: 0; }}
  li {{ margin-bottom: 7px; font-size: 14.5px; }}
  footer {{ padding: 4px 20px 32px; font-size: 11.5px; color: #64748b;
            max-width: 680px; margin: 0 auto; }}
</style></head>
<body>
  <header>
    <h1>Pure Tone Audiometry — Clinical Report {badge}</h1>
    <p>AudioSense AI · engine {html.escape(str(entry.get('engine') or 'offline-template'))}
       · reference {html.escape(h)}</p>
  </header>
  <main>
    <dl>{rows}</dl>
    {''.join(sections)}
  </main>
  <footer>
    {html.escape(entry.get('disclaimer') or '')}
    <br><br>This is the clinician's report. The patient counselling sheet is a
    separate document, issued with its own QR code.
  </footer>
</body></html>""")


@router.get("/verify/{h}")
def verify(h: str):
    entry = pdf.lookup_hash(h)
    if entry:
        # The report prose is served by /api/report-view/{h}, which renders it
        # for a reader. This endpoint answers only "is this hash one we
        # issued?", so it returns the provenance and not the clinical content —
        # a JSON dump of the findings here would be a second, unformatted copy
        # of the document on a route whose purpose is authenticity.
        provenance = {k: v for k, v in entry.items()
                      if k not in ("report", "disclaimer", "patient_header")}
        return {"valid": True, "hash": h, **provenance,
                "report_url": f"/api/report-view/{h}",
                "message": "This report was generated by AudioSense AI and its "
                           "contents match the recorded analysis."}
    return {"valid": False, "hash": h,
            "message": "Unknown hash — this report was not generated by this "
                       "AudioSense AI instance."}
