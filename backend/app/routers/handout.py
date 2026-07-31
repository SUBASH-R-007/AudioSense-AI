"""Patient handout: a QR code that puts the counseling sheet on the
patient's own phone.

A printed sheet gets folded into a pocket and lost. A QR scanned at the
counter opens the same plain-language summary, in the patient's language,
on the device they already carry — and can be shown to family members who
were not in the room.

The handout is served from this instance (works on a clinic LAN with no
internet) and keyed by the same verification hash used on the PDF.
"""
from __future__ import annotations

import html
import io
import json
from pathlib import Path

import qrcode
from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, Response

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HANDOUT_STORE = DATA_DIR / "handouts.json"


def _load() -> dict:
    if HANDOUT_STORE.exists():
        try:
            return json.loads(HANDOUT_STORE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


@router.post("/handout")
def create_handout(request: Request, payload: dict = Body(...)):
    """Store a counseling sheet and return its shareable URL + QR image URL."""
    from app.services.pdf import result_hash

    analysis = payload.get("analysis", {})
    h = result_hash(analysis)
    store = _load()
    store[h] = {
        "patient": (payload.get("patient") or {}).get("name", ""),
        "counseling": payload.get("counseling", {}),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HANDOUT_STORE.write_text(json.dumps(store, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    base = str(request.base_url).rstrip("/")
    return {
        "hash": h,
        "url": f"{base}/api/handout/{h}",
        "qr_url": f"{base}/api/qr?data={base}/api/handout/{h}",
    }


@router.get("/qr")
def qr(data: str):
    """Render any string as a QR PNG (server-side, no JS library needed)."""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/handout/{h}", response_class=HTMLResponse)
def view_handout(h: str):
    """Mobile-friendly counseling sheet — what the QR code opens."""
    entry = _load().get(h)
    if not entry:
        return HTMLResponse(
            "<h1>Handout not found</h1><p>This link was not issued by this "
            "AudioSense AI instance.</p>", status_code=404)

    counseling = entry.get("counseling", {})
    langs = [k for k in ("english", "tamil", "hindi", "telugu", "kannada", "malayalam")
             if isinstance(counseling.get(k), dict)]

    sections = []
    for i, lang in enumerate(langs):
        c = counseling[lang]
        items = "".join(f"<li>{html.escape(s)}</li>" for s in c.get("summary", []))
        tips = "".join(f"<li>{html.escape(s)}</li>" for s in c.get("tips", []))
        sections.append(f"""
        <section id="{lang}" class="lang" style="display:{'block' if i == 0 else 'none'}">
          <h2>{html.escape(c.get('heading', ''))}</h2>
          <ul class="summary">{items}</ul>
          <h3>{html.escape(c.get('tips_heading', 'Practical tips'))}</h3>
          <ul class="tips">{tips}</ul>
        </section>""")

    buttons = "".join(
        f'<button onclick="show(\'{l}\')">{html.escape(counseling[l].get("native", l))}</button>'
        for l in langs
    )

    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your Hearing Summary — AudioSense AI</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0;
         background: #f8fafc; color: #0f172a; line-height: 1.65; }}
  header {{ background: #0d9488; color: white; padding: 18px 20px; }}
  header h1 {{ margin: 0; font-size: 18px; }}
  header p {{ margin: 4px 0 0; font-size: 12.5px; opacity: .9; }}
  nav {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 16px;
         background: white; border-bottom: 1px solid #e2e8f0; }}
  nav button {{ border: 1px solid #cbd5e1; background: white; border-radius: 999px;
               padding: 6px 14px; font-size: 14px; cursor: pointer; }}
  main {{ padding: 16px; max-width: 640px; margin: 0 auto; }}
  section {{ background: white; border-radius: 14px; padding: 18px;
             box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  h2 {{ font-size: 17px; margin: 0 0 12px; }}
  h3 {{ font-size: 14px; color: #0d9488; margin: 18px 0 6px;
        text-transform: uppercase; letter-spacing: .05em; }}
  ul {{ padding-left: 20px; margin: 0; }}
  li {{ margin-bottom: 8px; font-size: 15.5px; }}
  footer {{ padding: 14px 20px 30px; font-size: 12px; color: #64748b;
            max-width: 640px; margin: 0 auto; }}
</style></head>
<body>
  <header>
    <h1>Your Hearing Summary</h1>
    <p>AudioSense AI · show this to your family and your doctor</p>
  </header>
  <nav>{buttons}</nav>
  <main>{''.join(sections)}</main>
  <footer>AI-assisted interpretation; final diagnosis requires a qualified
  audiologist. Reference: {html.escape(h)}</footer>
<script>
  function show(id) {{
    document.querySelectorAll('.lang').forEach(function (s) {{
      s.style.display = s.id === id ? 'block' : 'none';
    }});
  }}
</script>
</body></html>""")
