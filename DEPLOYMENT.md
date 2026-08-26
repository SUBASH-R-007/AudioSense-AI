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

| Platform | Free tier today | Verdict for a **pilot** |
|---|---|---|
| **Oracle Cloud Always Free** | 2 OCPU / 12 GB ARM, 200 GB block storage, 10 TB egress, region `ap-mumbai-1` | **Only option that clears all three bars.** No sleep, real persistence, India region. Needs a card for identity verification |
| Hugging Face Spaces | Static Spaces free; **compute Spaces now require a paid plan** | **No longer viable.** Was recommended here previously — that is now wrong. Its disk also wipes on the 48-hour sleep |
| Render | 512 MB, sleeps ~15 min idle | **No.** Cannot attach a disk at all on free, so records cannot persist, and a ~1 min cold start with a patient in the chair |
| Koyeb / Fly.io | — | **No.** Free tiers closed to new customers |
| Google Cloud Run | Generous always-free, scales to zero | Persistence needs Cloud SQL, which is **not** free. Cold start on a 250 MB image |
| Vercel (backend) | — | **No.** Dependency bundle far exceeds the function size limit |
| Clinic mini PC | ₹15,000–25,000 one-off | Best latency and PHI control. Honest cost: ~25–41 months of the cheapest cloud VM |

**Frontend:** Cloudflare Pages free — unlimited bandwidth, 25 MiB per file.
Not Vercel Hobby: its licence prohibits commercial use, and a clinical pilot is
not hobby use.

> Free-tier terms change often, and silently — Oracle halved the ARM allowance
> from 4 OCPU/24 GB to 2 OCPU/12 GB in June 2026 by editing the docs page, with
> no announcement. Re-check before you rely on any of this.

---

## Railway + Vercel — the quickest path

Chosen for the first pilot. Railway is **not free** — a one-time $5 trial credit
lasting 30 days, then Hobby at $5/month — and Vercel's Hobby plan is licensed
for non-commercial use, so a clinic running on it should be on a paid plan.
Both are deliberate trade-offs for speed of setup; the Oracle walkthrough below
is the free alternative.

Railway does have the one thing that matters most here: **real persistent
volumes**. Configure that and the rest is ordinary.

### 1. Backend on Railway

1. **New Project → Deploy from GitHub repo** → pick the repo.
2. **Settings → Root Directory: `backend`** ← required. Railway then finds
   `backend/Dockerfile` and uses it; there is no `railway.json` or Procfile in
   this repo on purpose, because the Dockerfile is the single deploy path.
3. **Settings → Networking → Generate Domain.** Note the
   `*.up.railway.app` URL — the frontend needs it.

### 2. The volume — do this before the first patient

**Settings → Volumes → New Volume**, mount path `/state`.

Then set the variables (**Variables** tab):

| Variable | Value |
|---|---|
| `AUDIOSENSE_STATE_DIR` | `/state` |
| `AUDIOSENSE_USERS` | `clinician:pbkdf2_sha256$600000$...` from `scripts/make_user.py` |
| `AUDIOSENSE_SECRET` | a long random value |
| `CORS_ORIGINS` | your Vercel URL, no trailing slash |
| `AUDIOSENSE_TRUSTED_PROXIES` | Railway's ingress address — see below |

Without `AUDIOSENSE_STATE_DIR` the volume is mounted and ignored, and records
still vanish on redeploy. **Do not** set the mount path to `/app/data`: that
directory holds the committed model artifacts, and mounting over it stops the
container booting.

`$PORT` is injected by Railway and the Dockerfile already reads it. Nothing to
configure.

### 3. Frontend on Vercel

1. **Add New → Project** → import the repo.
2. **Root Directory: `frontend`** ← required. The Vite preset and build
   settings come from `frontend/vercel.json`.
3. **Environment Variables** → `VITE_API_BASE_URL` = the Railway URL.
   Read at **build** time, so changing it needs a redeploy, not a restart.
4. Deploy, then set `CORS_ORIGINS` on Railway to the resulting Vercel URL.

The 11 anatomy clips (22 MB) ship in `dist/` as ordinary static assets — no
extra configuration, and the SPA rewrite in `vercel.json` does not shadow them
because Vercel serves real files before applying rewrites.

### 4. The throttle behind Railway's proxy

Every request reaches the app from Railway's ingress, so the socket address is
the same for everyone and the login throttle would put the whole clinic in one
bucket. Set `AUDIOSENSE_TRUSTED_PROXIES` to the peer address the app actually
sees. Find it once, from the logs of a failed login, or leave it unset and
accept that eight failed attempts across all users triggers a shared five-minute
wait.

### 5. Verify before the first patient

- [ ] Save a visit → **Deployments → Redeploy** → the visit is still in
      `/records`. This is the one that proves the volume is working.
- [ ] `/api/health` returns `"model_trained": true`
- [ ] Sign-in works; an unauthenticated request to `/api/records/patients` is refused
- [ ] An anatomy clip plays on the dashboard
- [ ] Back up the volume on a schedule — Railway does not do it for you

### What to watch

- **The trial credit expires after 30 days.** When it does the service stops,
  and the volume is retained only while the project is active. Move to Hobby
  before the pilot starts, or plan the migration.
- **Redeploys restart the container.** With the volume configured that is
  harmless; without it, it is silent data loss.

---

## Pilot walkthrough — Oracle Always Free + Cloudflare Pages

The demo path below (Step 1/2/3) puts the app on the internet. This section is
what a **pilot with real patients** additionally needs: storage that survives,
no cold start, and the data staying in India.

Budget about **90 minutes**, most of it waiting on Oracle.

### A. Persisting patient data — do this first

Nothing else matters if the records evaporate. One variable does it:

```
AUDIOSENSE_STATE_DIR=/state
```

and run the container with a volume mounted there:

```bash
docker run -d --restart unless-stopped \
  -p 8000:8000 -e PORT=8000 \
  -v /mnt/audiosense:/state \
  -e AUDIOSENSE_STATE_DIR=/state \
  -e AUDIOSENSE_USERS='clinician:pbkdf2_sha256$600000$...' \
  -e AUDIOSENSE_SECRET='<long random value>' \
  -e CORS_ORIGINS='https://your-frontend.pages.dev' \
  audiosense-api
```

Five files move onto the volume: `records.db`, `verify_store.json`,
`handouts.json`, `feedback.jsonl`, `ai_config.json`. The model artifacts stay
in the image, which is why the variable exists rather than mounting `/app/data`.

Verify it before seeing a patient — save a visit, restart, and look again:

```bash
docker restart <container>
# then open /records in the app; the visit must still be listed
```

### B. Oracle Cloud — the VM

1. **cloud.oracle.com → Start for free.** Pick **India South (Hyderabad)** or
   **India West (Mumbai)** as your home region. **This is permanent** — it
   cannot be changed later, and it is what keeps patient data in-country.
2. Identity verification needs a card. It is a hold, not a charge, unless you
   later upgrade to Pay-As-You-Go.
3. **Compute → Instances → Create.** Shape **VM.Standard.A1.Flex**, 2 OCPU /
   12 GB, image **Ubuntu 22.04 (aarch64)**. Save the SSH key.
   *If you get "Out of host capacity", that is chronic — retry over a few days,
   or fall back to the mini PC below.*
4. **Storage → Block Volumes → Create**, 50 GB, attach it to the instance, then
   format and mount it at `/mnt/audiosense`.
5. **Networking → Security List** → allow ingress on 80 and 443. Also open them
   in the guest firewall: `sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT`
   (Oracle images ship with a restrictive default).

### C. Build on the VM, not locally

The VM is ARM. Build the image on it — cross-building with QEMU is slow and
occasionally produces subtly broken wheels:

```bash
sudo apt update && sudo apt install -y docker.io git
git clone https://github.com/SUBASH-R-007/AudioSense-AI.git
cd AudioSense-AI
sudo docker build -t audiosense-api ./backend
```

All the Python dependencies publish `aarch64` wheels, so this is a normal build.

### D. TLS

The browser needs HTTPS — the simulator and the screening test use the Web Audio
and microphone APIs, which browsers refuse on plain HTTP. Point a domain at the
VM's public IP and let Caddy handle certificates:

```bash
sudo apt install -y caddy
# /etc/caddy/Caddyfile
api.your-domain.org {
    reverse_proxy localhost:8000
}
```

Then set `AUDIOSENSE_TRUSTED_PROXIES=127.0.0.1`, because Caddy is now the peer
and the login throttle must read the forwarded address from it rather than
seeing every request as coming from localhost.

### E. Frontend on Cloudflare Pages

1. **dash.cloudflare.com → Workers & Pages → Create → Pages → Connect to Git.**
2. Build command `npm run build`, output directory `dist`, **root directory
   `frontend`**.
3. Environment variable `VITE_API_BASE_URL=https://api.your-domain.org`
   — read at **build** time, so changing it needs a redeploy, not a restart.
4. Back on the backend, set `CORS_ORIGINS` to the Pages URL and restart.

### F. Before the first patient

- [ ] Save a visit, restart the container, confirm it is still there
- [ ] Sign in works, and signing out clears the case
- [ ] `/api/health` returns 200 and `"model_trained": true`
- [ ] An anatomy clip plays on the dashboard
- [ ] A PDF report generates and its QR opens the handout on a phone
- [ ] Take a backup: `sqlite3 /mnt/audiosense/records.db ".backup /mnt/audiosense/backup-$(date +%F).db"` — put it on a cron

### What free infrastructure will not give you

Say these out loud before the pilot starts, not after:

- **Oracle reclaims "idle" instances.** Under 20% CPU *and* network *and* memory
  across 7 days marks an Always Free instance idle; it is **stopped, and nothing
  restarts it on a request**. A quiet clinic qualifies. Upgrading the tenancy to
  Pay-As-You-Go exempts you — and makes the card genuinely billable.
- **No SLA, no support, no BAA or DPA.** Always-Free-only tenancies are not
  eligible for Oracle Support. There is no contractual recourse.
- **No automatic backups.** The cron line above is the whole backup story.
- **Under the DPDP Act 2023 the clinic is the Data Fiduciary** and carries the
  statutory liability regardless of who hosts the server.
- **Every signed-in user sees every patient.** There are no roles and no audit
  trail — see §4 of [SCALING.md](SCALING.md). Fine for one clinic and a handful
  of named accounts; not fine for two clinics sharing an instance.

### Fallback: a mini PC in the clinic

If Mumbai and Hyderabad have no A1 capacity, or the card is a problem: an Intel
N100 mini PC (16 GB / 512 GB, ₹15,000–25,000) runs the existing image unmodified
because it is x86-64. Enable BIOS auto-power-on, and use **Tailscale** for remote
access — not Cloudflare Tunnel, which terminates TLS at the edge and sends PHI
out of the country. Frontend still on Pages.

Be honest about the economics: that is 25–41 months of the cheapest always-on
cloud VM. Justify it on persistence, latency and PHI control, never on cost.

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

### Hugging Face Spaces — NO LONGER FREE FOR THIS APP

Kept for reference only. Creating a Space that runs compute now
requires a paid plan, and the disk is wiped on every sleep, so
patient records would not survive a quiet weekend.

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
Container filesystems are ephemeral, so `records.db`, handouts, report
verification and clinician feedback reset. Fine for a demo; **data loss for a
pilot**, and the dashboard still says "Saved".

Set `AUDIOSENSE_STATE_DIR` to a mounted volume — see *Persisting patient data*
below.

**Do NOT mount the volume at `/app/data`.** That directory also holds the
committed model artifacts (`model_bundle.joblib`, `otoscopy_model.joblib`,
`deep_ensemble.joblib`, `otoscope_reference/`), and mounting over it hides them
so the app cannot start. `AUDIOSENSE_STATE_DIR` exists precisely to separate the
writable half from the read-only half.

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
| **`AUDIOSENSE_STATE_DIR`** | **yes for a pilot** | **Directory for everything the app writes** — patient database, handouts, report verification, feedback, provider config. Point it at a mounted volume or records vanish on redeploy. Unset = the in-image path, which is ephemeral. Never set it to `/app/data` |
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
