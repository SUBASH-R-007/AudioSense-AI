# Deployment — Vercel (frontend) + any Docker host (backend)

**Local development is unaffected by any of this.** With no environment
variables set, the frontend keeps using relative `/api` paths through the Vite
dev proxy exactly as before. The production settings are additive.

There is **one** backend deployment path: `backend/Dockerfile`. It is
self-contained, reads `$PORT`, and works unchanged on every platform below —
no per-platform config files to drift out of sync.

---

## How the split works

```
Vercel  ──  static React build          (https://your-app.vercel.app)
                │  fetch(VITE_API_BASE_URL + '/api/...')
                ▼
Docker host ──  FastAPI + model          (https://your-api.example.com)
```

Two settings connect them, and they must agree:

| Where | Variable | Value |
|---|---|---|
| Frontend host | `VITE_API_BASE_URL` | the backend URL |
| Backend host | `CORS_ORIGINS` | the frontend URL |

Get either wrong and the browser blocks every request. **Deploy the backend
first** so you have its URL.

---

## Picking a free backend host

The backend needs Python, ~250 MB of dependencies (scikit-learn, OpenCV,
matplotlib, reportlab) and a 7.5 MB model to load.

**The model artifacts are committed (~9 MB).** Training peaks near 500 MB of
memory — at or above the ceiling of most free tiers — so building the model on
deploy fails unpredictably. Shipping it makes every option below viable.

| Platform | Free tier | Sleeps? | Verdict |
|---|---|---|---|
| **Hugging Face Spaces** | 2 vCPU, **16 GB RAM** | after long inactivity | **Best choice.** Most memory by far, no card required, and an ML project hosted on HF reads well to a technical jury |
| **Koyeb** | 512 MB, 1 service | no | Good if you want it always warm |
| **Render** | 512 MB | ~15 min idle, ~50 s cold start | Reliable; just point it at the Dockerfile |
| **Fly.io** | small shared VM | configurable | Solid, needs a card |
| **Google Cloud Run** | generous always-free | scales to zero | Very reliable; needs GCP billing enabled |
| **Back4App Containers** | free container tier | varies | Straightforward Docker deploy |
| **Oracle Cloud Always Free** | 4 ARM cores, 24 GB | no | Most powerful, but you administer a VM |
| **Vercel Python functions** | — | — | **Not viable** — the dependency bundle far exceeds the size limit |

> Free-tier terms change often. Check current limits before relying on any of
> them for a judged demo.

---

## Step 1 — backend

### Test the image locally first

```bash
docker build -t audiosense-api ./backend
docker run -p 8000:8000 -e PORT=8000 audiosense-api
```

Open <http://localhost:8000/> — you should see
`{"service":"AudioSense AI","status":"ok","model_trained":true}`.
If that works, it will work anywhere.

### Hugging Face Spaces (recommended)

1. **huggingface.co → New Space → SDK: Docker → Blank**, visibility **Public**
   (private Spaces sleep more aggressively).
2. A Space is a git repository. Copy the backend into it:

```bash
git clone https://huggingface.co/spaces/<username>/audiosense-api
cd audiosense-api
cp -r /path/to/AudioSense-AI/backend/* .
```

3. Spaces route to port **7860**, so create a `README.md` in the Space with
   this header:

```yaml
---
title: AudioSense AI API
sdk: docker
app_port: 7860
---
```

4. Point the container at that port and push:

```bash
echo "ENV PORT=7860" >> Dockerfile
git add -A && git commit -m "AudioSense AI backend" && git push
```

5. **Settings → Variables and secrets** → add `CORS_ORIGINS` once you have the
   frontend URL.

Your API lands at `https://<username>-audiosense-api.hf.space`.

### Koyeb / Render / Fly / Cloud Run / Back4App

All of them accept the Dockerfile directly:

- **Koyeb** — Create Service → GitHub → Dockerfile, work directory `backend`
- **Render** — New Web Service → Runtime **Docker**, root directory `backend`
- **Fly.io** — `cd backend && fly launch` (it detects the Dockerfile)
- **Cloud Run** — `gcloud run deploy --source backend --allow-unauthenticated`
- **Back4App** — New Container App → repo → Dockerfile path `backend/Dockerfile`

Set `CORS_ORIGINS` in whichever dashboard you use. Nothing else is required —
`$PORT` and the health check at `/` are already handled.

---

## Step 2 — Vercel (frontend)

1. **Add New → Project** → import the repo.
2. **Root Directory: `frontend`** ← required.
   Framework preset **Vite** is detected; build and output come from
   `frontend/vercel.json`.
3. **Environment Variables**, for all environments:

   | Variable | Value |
   |---|---|
   | `VITE_API_BASE_URL` | your backend URL, no trailing slash |

4. **Deploy.**

> `VITE_API_BASE_URL` is read at **build** time. Changing it requires a
> redeploy — restarting does nothing.

---

## Step 3 — close the loop

Set `CORS_ORIGINS` on the backend to your real Vercel URL and redeploy it.
Until you do, the browser blocks requests even though the API is healthy.

To also allow Vercel's per-branch preview URLs, set:

```
CORS_ORIGIN_REGEX = https://.*\.vercel\.app
```

---

## Verify

1. Open the Vercel URL — the sidebar should show **Offline mode**.
2. **New Test → Noise Notch → Analyze** — a verdict banner appears.
3. DevTools → Network: requests go to the backend host, not Vercel.
4. **Simulator** and **Listening Lab** need HTTPS for audio and microphone;
   both platforms serve HTTPS.

---

## Troubleshooting

**CORS error in the console**
The frontend URL is not in `CORS_ORIGINS`. Check for a trailing slash, `http`
vs `https`, and that you redeployed after changing it. The backend root route
echoes `allowed_origins`, so you can see exactly what it accepts.

**Requests go to the frontend domain instead of the backend**
`VITE_API_BASE_URL` was missing at build time. Set it and **redeploy**.

**`"model_trained": false`**
`backend/data/model_bundle.joblib` did not reach the container — usually a
wrong build context or a `.dockerignore` in a copied Space that excludes it.
As a last resort `python -m scripts.ensure_model` retrains it, but that needs
roughly 500 MB of memory and will fail on a 512 MB tier.

**`ImportError: libGL.so.1`**
An OpenCV system dependency. The Dockerfile installs `libgl1` and
`libglib2.0-0`; this only appears if you deploy without the Dockerfile.

**Patient records disappear after a redeploy**
Expected — container filesystems are ephemeral, so `records.db`, handouts and
clinician feedback reset. Mount a volume at `/app/data` for persistence; the
demo does not need it.

**Tamil text missing from the PDF**
The Linux image has no Tamil font, so the PDF prints a note instead. The Tamil
counselling sheet still displays and reads aloud correctly in the app. Add a
Noto Tamil font to the image to fix it.

**Cold starts**
Free tiers sleep. Open the backend URL a minute before demoing so the first
real request is fast.

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

To test a production build locally:

```bash
cd frontend
npm run build
npm run preview          # :4173, already an allowed CORS origin
```

---

## Access control — do this before the first deploy

The instance holds patient records. It ships **locked**: with nothing
configured, every API request is refused with a 503 rather than served. That is
deliberate — an operator who forgets this section gets a support call, not a
breach.

**1. Create an account.** On your machine, in `backend/`:

```bash
python -m scripts.make_user clinician
```

It asks for a password twice, echoes nothing, and prints two values.

**2. Put them in the backend's environment**, alongside `CORS_ORIGINS`:

```
AUDIOSENSE_USERS=clinician:pbkdf2_sha256$600000$....$....
AUDIOSENSE_SECRET=<the long random value the script printed>
```

More people, same variable, comma-separated:

```
AUDIOSENSE_USERS=alice:pbkdf2_sha256$...,bob:pbkdf2_sha256$...
```

**3. Confirm it took.** After redeploying:

```bash
curl -s https://your-backend/api/auth/status
```

`{"mode":"protected", ...}` is what you want. `"locked"` means the variable did
not arrive. `"anonymous"` means `AUDIOSENSE_ALLOW_ANONYMOUS` is set — remove it.

Then check the door is actually shut:

```bash
curl -s -o /dev/null -w '%{http_code}
' https://your-backend/api/records/patients
```

`401` is correct. `200` means you are serving patient records to the internet.

### What this does and does not do

| | |
|---|---|
| Protected | Every API route, plus `/docs`, `/redoc` and `/openapi.json` |
| Public by design | `/api/health` (uptime probes), `/api/auth/status`, `/api/auth/login`, `/` (banner), `/api/qr`, `/api/handout/{h}` and `/api/verify/{h}` (a patient opens these by scanning the QR on their printed report — protecting them would mean issuing patients accounts), `/api/otoscopy/image/...` (reference atlas photographs, no patient data, loaded as `<img>`) |
| Sessions | Signed with `AUDIOSENSE_SECRET`, valid 12 hours, held in `sessionStorage` so they die with the browser tab |
| Removing access | Delete the entry from `AUDIOSENSE_USERS` and restart. Their existing sessions stop working immediately — the token is re-checked against the account list on every request |
| Revoking everything | Rotate `AUDIOSENSE_SECRET`. Every session everywhere is invalidated |

**What it is not.** One shared account per role, no per-user audit trail, no
password reset, no lockout that survives a restart, and no roles — everyone who
signs in can see everything. It stops strangers; it does not tell two
clinicians apart. Section 4 of [SCALING.md](SCALING.md) covers what a
multi-clinic deployment needs beyond this.

### The login throttle, and `AUDIOSENSE_TRUSTED_PROXIES`

Eight failed logins for one account from one address make that pair wait five
minutes. The counter is in-process, so it resets on restart and is not shared
between replicas; it raises the cost of guessing rather than preventing it.

The bucket is keyed on **(client address, username)**. The address half is
taken from the socket, *not* from `X-Forwarded-For` — that header is written by
the caller, and a throttle keyed on something the caller chooses is not a
throttle. Honouring it unconditionally broke the control in both directions:
rotating the header bought unlimited guesses, and setting it to somebody else's
address filled *their* bucket and locked them out of their own instance.

Behind a platform ingress (Hugging Face Spaces, Koyeb, a load balancer) every
request arrives from the proxy, so the socket address is the same for everyone
and the whole clinic would share one bucket. Set:

```
AUDIOSENSE_TRUSTED_PROXIES=10.0.0.1,10.0.0.2
```

to the ingress addresses. The header is then read only for requests that
genuinely arrive from one of them, and only its **rightmost** entry — the hop
that trusted proxy appended itself. The leftmost entry is whatever the client
sent and is never used. Leave it unset when nothing sits in front of the app.

**`/api/verify/{h}` still returns the patient's name** to anyone holding a valid
report hash, because that is how someone checks a printout is genuine. The hash
is 64 bits and not enumerable, but it is the one place a name is reachable
without a login. Say so if that is unacceptable for your setting and it can be
reduced to a yes/no.

---

## Environment variables

### Backend

| Variable | Required | Purpose |
|---|---|---|
| **`AUDIOSENSE_USERS`** | **yes in prod** | **Accounts. Without it the instance refuses every request.** `name:hash,name:hash` — mint each with `python -m scripts.make_user <name>` |
| **`AUDIOSENSE_SECRET`** | **yes in prod** | **Session signing key.** Unset means a random key per process: sessions drop on restart and are not shared between replicas |
| `AUDIOSENSE_SESSION_HOURS` | no | Session lifetime, default 12. Read at call time, so it works from `backend/.env` as well as from a real environment variable |
| `AUDIOSENSE_ALLOW_ANONYMOUS` | **never in prod** | `1` disables the login entirely. For local development only |
| `AUDIOSENSE_TRUSTED_PROXIES` | recommended behind a proxy | Peer addresses whose `X-Forwarded-For` may be believed, comma-separated. See below |
| `PORT` | auto | Injected by the platform; the Dockerfile uses it |
| `CORS_ORIGINS` | yes in prod | Comma-separated allowed origins |
| `CORS_ORIGIN_REGEX` | no | Regex for preview domains |
| `MPLCONFIGDIR` | set in image | `/tmp/matplotlib` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` | no | Setting any one switches the AI engine to API mode on boot. Leave unset for the offline engine. |

### Frontend

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | yes in prod | Backend URL, no trailing slash |

---

## A note for the demo

The app is **offline-first by design** and works fully with no API key. If you
set a provider key, the backend boots into API mode and every report makes a
network round-trip; if that key has no quota the request fails and falls back
to the offline engine — correct behaviour, but it costs a wasted round-trip
and shows a warning toast.

For a clean demo, leave provider keys unset, or open **AI Engine → Offline
Mode → Save** once in the app (a saved setting overrides the environment).
