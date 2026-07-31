# Deployment — Vercel (frontend) + Railway (backend)

**Local development is unaffected by any of this.** With no environment
variables set, the frontend keeps using relative `/api` paths through the Vite
dev proxy exactly as before. The production settings are additive.

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

## Step 1 — Railway (backend)

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

`backend/railway.json` runs, in order:

```
python -m app.ml.generate_dataset   # 12,000 synthetic audiograms
python -m app.ml.train              # RandomForest + calibration + OOD
python -m app.ml.deep               # optional neural ensemble
```

The model artifacts are gitignored, so **the build creates them**. Expect the
first deploy to take roughly 3–5 minutes. The deep-ensemble step is wrapped so
that if it fails, the deploy still succeeds — only `/api/model/comparison`
returns 503.

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
Training was skipped or ran out of memory. Check the Railway build log. On a
low-memory plan, commit the artifacts instead:

```bash
git add -f backend/data/model_bundle.joblib backend/data/dataset.csv
git commit -m "Commit model artifacts for low-memory deployment"
```

Then remove the training steps from `railway.json`'s `buildCommand`.

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
