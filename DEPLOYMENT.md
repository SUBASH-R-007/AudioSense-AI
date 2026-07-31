# Deployment — Vercel (frontend) + a free backend host

**Local development is unaffected by any of this.** With no environment
variables set, the frontend keeps using relative `/api` paths through the Vite
dev proxy exactly as before. The production settings are additive.

---

## Picking a free backend host

The frontend is trivial to host — Vercel's free tier covers it comfortably.
The backend is the part with constraints: Python, ~250 MB of dependencies
(scikit-learn, OpenCV, matplotlib, reportlab), and a 7.5 MB model to load.

**The model artifacts are committed to the repository (~8 MB total.)** Training
peaks near 500 MB of memory, which is at or above the ceiling of most free
tiers, so building the model on deploy fails unpredictably. Shipping it makes
every option below viable and keeps deploys fast.

| Platform | Free tier | Sleeps? | Verdict for this project |
|---|---|---|---|
| **Hugging Face Spaces** | 2 vCPU, **16 GB RAM** | after long inactivity | **Best choice.** Most memory by far, no card required, and an ML project hosted on HF reads well to a technical jury |
| **Render** | 512 MB RAM | after ~15 min idle, ~50 s cold start | Closest to Railway. Works because the model is pre-built. `render.yaml` is included |
| **Koyeb** | 512 MB, 1 service | no | Good if you want it always warm |
| **Fly.io** | small shared VM | configurable | Solid, but needs a card and more setup |
| **Google Cloud Run** | generous always-free | scales to zero | Very reliable; needs a GCP account with billing enabled |
| **Oracle Cloud Always Free** | 4 ARM cores, 24 GB | no | Most powerful, but you administer a whole VM |
| **Vercel Python functions** | — | — | **Not viable.** The dependency bundle far exceeds the size limit, and there is no persistent filesystem |

> Free-tier terms change often. Check the current limits before relying on any
> of them for a judged demo.

**Recommendation:** Hugging Face Spaces for the backend, Vercel for the
frontend. Instructions for both are below, and the included `Dockerfile` also
works unchanged on Koyeb, Fly, Cloud Run and Back4App.

---

## Option A — Hugging Face Spaces (recommended)

1. Go to **huggingface.co → New Space**.
   - **SDK: Docker** → *Blank*
   - Visibility: **Public** (private Spaces sleep more aggressively)
2. The Space is a git repository. Push the backend into it:

```bash
git clone https://huggingface.co/spaces/<your-username>/audiosense-api
cd audiosense-api
cp -r /path/to/AudioSense-AI/backend/* .
```

3. Spaces expect the container to listen on **7860**, so add this line to the
   top of the copied `README.md` (create it if absent):

```yaml
---
title: AudioSense AI API
sdk: docker
app_port: 7860
---
```

4. Set the port and push:

```bash
echo "ENV PORT=7860" >> Dockerfile
git add -A && git commit -m "AudioSense AI backend" && git push
```

5. In **Settings → Variables and secrets**, add `CORS_ORIGINS` with your Vercel
   URL once you have it.

Your API is at `https://<username>-audiosense-api.hf.space`.

## Option B — Render

1. **New → Blueprint**, point it at the repo. `render.yaml` at the root
   configures everything (root directory, build, start command, health check).
2. Or **New → Web Service** manually: **Root Directory `backend`**,
   build `pip install -r requirements.txt && python -m scripts.ensure_model`,
   start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Add `CORS_ORIGINS` in the dashboard once the frontend is deployed.

**Note the cold start.** A free Render service sleeps after ~15 minutes idle
and takes roughly 50 seconds to wake. Open the backend URL a minute before
demoing.

## Option C — anything that takes a Dockerfile

`backend/Dockerfile` is self-contained and reads `$PORT`:

```bash
docker build -t audiosense-api ./backend
docker run -p 8000:8000 -e PORT=8000 audiosense-api
```

Koyeb, Fly.io, Cloud Run and Back4App all accept it as-is. Set `CORS_ORIGINS`
in whichever dashboard you use.

---

## How the split works

```
Vercel  ──  static React build            (https://your-app.vercel.app)
                │  fetch(VITE_API_BASE_URL + '/api/...')
                ▼
Railway ──  FastAPI + model artifacts     (https://your-api.up.railway.app)
```

Two settings connect them, and they must agree:

| Where | Variable | Value |
|---|---|---|
| Vercel | `VITE_API_BASE_URL` | the Railway URL |
| Railway | `CORS_ORIGINS` | the Vercel URL |

Get either wrong and the browser blocks every request. Deploy the backend
first so you have its URL.

---

## Option D — Railway (if you still have credit)

1. **New Project → Deploy from GitHub repo →** select `AudioSense-AI`.
2. Open the service → **Settings**:
   - **Root Directory:** `backend`  ← *required, or Railway will not find the app*
   - Build and start commands come from `backend/railway.json` automatically.
3. **Variables** → add:

   | Variable | Value |
   |---|---|
   | `CORS_ORIGINS` | `https://your-app.vercel.app` *(fill in after step 2; redeploy then)* |
   | `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` *(optional — allows Vercel preview builds)* |
   | `MPLCONFIGDIR` | `/tmp` *(keeps matplotlib quiet on a read-only home)* |

4. **Settings → Networking → Generate Domain.** Copy the URL.

### What the build does

`backend/railway.json` runs `python -m scripts.ensure_model`, which finds the
committed artifacts and exits immediately. If they are ever missing it trains
them instead, so a slim checkout still deploys.

### Verify

Open `https://your-api.up.railway.app/` — you should see:

```json
{ "service": "AudioSense AI", "status": "ok", "model_trained": true }
```

`"model_trained": false` means training did not finish — see troubleshooting.
Interactive API docs are at `/docs`.

---

## Step 2 — Vercel (frontend)

1. **Add New → Project →** import the same repo.
2. Configure:
   - **Root Directory:** `frontend`  ← *required*
   - Framework preset: **Vite** (auto-detected)
   - Build command `npm run build`, output `dist` — already in `frontend/vercel.json`
3. **Environment Variables** → add for **all** environments:

   | Variable | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://your-api.up.railway.app` (no trailing slash) |

4. **Deploy.**

> `VITE_API_BASE_URL` is read at **build** time, not runtime. If you change it
> you must redeploy — restarting does nothing.

---

## Step 3 — close the loop

Go back to Railway and set `CORS_ORIGINS` to your real Vercel URL, then
redeploy the backend. Until you do, the browser will block requests with a
CORS error even though the API itself is healthy.

---

## Verify the deployment

1. Open the Vercel URL. The sidebar should show **Offline mode**.
2. **New Test → Noise Notch → Analyze.** A verdict banner appears.
3. Open DevTools → Network: requests should go to the Railway host, not Vercel.
4. **Listening Lab** and **Simulator** need HTTPS for microphone and audio —
   both platforms serve HTTPS, so this works.

---

## Troubleshooting

**CORS error in the console**
The Vercel URL is not in `CORS_ORIGINS`. Check for a trailing slash, `http` vs
`https`, and that you redeployed Railway after changing it. Visit the backend
root — it echoes `allowed_origins` so you can see exactly what it accepts.

**Requests go to the Vercel domain instead of Railway**
`VITE_API_BASE_URL` was missing at build time. Set it and **redeploy**.

**`"model_trained": false`**
The committed `backend/data/model_bundle.joblib` did not reach the server —
usually a wrong root directory, or a `.dockerignore`/`.gitignore` in a copied
Space that excludes it. Confirm the file is present in the deployed tree. As a
last resort, `python -m scripts.ensure_model` will retrain it, but that needs
roughly 500 MB of memory and will fail on a 512 MB tier.

**Build fails with `ImportError: libGL.so.1`**
An OpenCV system dependency. The included `Dockerfile` installs `libgl1` and
`libglib2.0-0`; if you are on a buildpack platform without them, switch that
service to the Dockerfile.

**Patient records disappear after a redeploy**
Expected. Railway's filesystem is ephemeral, so `records.db`, saved handouts
and clinician feedback reset on every deploy. Attach a Railway **Volume**
mounted at `/app/data` for persistence — the demo does not need it.

**Tamil text missing from the PDF**
The Linux container has no Tamil font, so the PDF prints a note instead. The
Tamil counselling sheet still displays and reads aloud correctly in the app.
To fix, add a Noto Tamil font to the image and point `pdf.py` at it.

**Cold starts**
Railway may sleep an idle service on some plans. Open the backend URL a minute
before demoing so the first real request is fast.

---

## Running locally (unchanged)

Do **not** create `frontend/.env`. With `VITE_API_BASE_URL` unset the app uses
relative paths and the dev proxy.

```bash
# terminal 1
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend
npm run dev
```

To test a production build locally without deploying:

```bash
cd frontend
npm run build
npm run preview          # serves on :4173, already an allowed CORS origin
```

---

## Environment variables reference

### Backend (Railway)

| Variable | Required | Purpose |
|---|---|---|
| `PORT` | auto | Injected by Railway; the start command uses it |
| `CORS_ORIGINS` | yes in prod | Comma-separated allowed origins |
| `CORS_ORIGIN_REGEX` | no | Regex for Vercel preview domains |
| `MPLCONFIGDIR` | recommended | `/tmp` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` | no | Setting any one switches the AI engine to API mode on boot. Leave unset for the offline engine. |

### Frontend (Vercel)

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | yes in prod | Railway backend URL, no trailing slash |

---

## A note for the demo

The app is **offline-first by design**: the deployed version works fully with
no API key. If you set a provider key on Railway, the backend boots into API
mode and every report makes a network round-trip. Should that key have no
quota, the request fails and falls back to the offline engine — correct
behaviour, but it costs a wasted round-trip and shows a warning toast.

For a clean demo, either leave the provider keys unset, or open **AI Engine →
Offline Mode → Save** in the app once (a saved setting overrides the
environment variable).
