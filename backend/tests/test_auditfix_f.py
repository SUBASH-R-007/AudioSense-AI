"""Screening procedure, catch trials, the otoscopy atlas and the results page.

The screening estimators run in the browser, so the procedure checks here run
the frontend's own modules under Node (skipped when Node is not installed)
and score them against expectations computed in Python from the listener
model — never from the estimator being tested. The rest are source checks on
the components, plus the API behaviour the otoscopy atlas depends on.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from statistics import NormalDist

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"
BAYES_JS = FRONTEND / "audio" / "bayesianThreshold.js"
TONE_JS = FRONTEND / "audio" / "toneAudiometer.js"
RUNNER = FRONTEND / "components" / "ScreeningRunner.jsx"
OTOSCOPY = FRONTEND / "pages" / "Otoscopy.jsx"
VERDICT_BANNER = FRONTEND / "components" / "VerdictBanner.jsx"

client = TestClient(app)

MIN_DB, MAX_DB = -10, 90


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ Node ---

HARNESS = r"""
import { pathToFileURL } from 'node:url'
const [, , bayesPath, tonePath, cfgJson] = process.argv
const { BayesianThreshold } = await import(pathToFileURL(bayesPath).href)
const { Staircase } = await import(pathToFileURL(tonePath).href)
const cfg = JSON.parse(cfgJson)

// Driven exactly as ScreeningRunner drives them.
function runBayes(respond) {
  const est = new BayesianThreshold(-10, 90, 30)
  let guard = 0
  while (!est.done && guard++ < 200) {
    const L = est.nextLevel()
    est.record(L, respond(L))
  }
  return { threshold: est.summary().threshold, done: est.done,
           trials: est.trials.map((t) => [t.level, t.heard]) }
}
function runStair(respond) {
  const est = new Staircase(40, -10, 90)
  let guard = 0
  while (!est.done && guard++ < 200) est.record(respond(est.level))
  return { threshold: est.threshold, presentations: est.presentations }
}

const out = {}

// Listeners who respond if and only if a tone is played at or above T.
out.deterministic = {}
for (const T of cfg.deterministic) {
  out.deterministic[T] = { bayes: runBayes((L) => L >= T), stair: runStair((L) => L >= T) }
}

// The reported value for a posterior concentrated at a single T.
out.mapping = {}
for (const T of cfg.mapping) {
  const est = new BayesianThreshold(-10, 90, 30)
  est.post = est.grid.map((t) => (t === T ? 1 : 0))
  out.mapping[T] = est.summary().threshold
}

// Noisy listeners: 4 dB cumulative-normal spread, 3% lapses, 2% false alarms,
// with T the level responded to exactly half the time.
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
function erf(x) {
  const s = Math.sign(x); x = Math.abs(x)
  const t = 1 / (1 + 0.3275911 * x)
  return s * (1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
    - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x))
}
const Phi = (z) => 0.5 * (1 + erf(z / Math.SQRT2))
const rT = mulberry32(cfg.seed), rB = mulberry32(cfg.seed + 1), rS = mulberry32(cfg.seed + 2)
out.noisy = []
for (let i = 0; i < cfg.noisy_n; i++) {
  const T = Math.floor(rT() * 71)
  const mu = T - cfg.mu_offset
  const p = (L) => 0.02 + 0.95 * Phi((L - mu) / 4)
  out.noisy.push([T, runBayes((L) => rB() < p(L)).threshold,
                  runStair((L) => rS() < p(L)).threshold])
}
console.log(JSON.stringify(out))
"""

#: The listener the screening procedure was checked against in the browser:
#: right 15/20/30/45/60/65, left 10/10/10/10/25/10 dB HL at 250 Hz-8 kHz.
AUDIT_LISTENER = [15, 20, 30, 45, 60, 65, 10, 10, 10, 10, 25, 10]

#: Listener model shared with the harness.
SIGMA, LAPSE, FALSE_ALARM = 4.0, 0.03, 0.02
MU_OFFSET = SIGMA * NormalDist().inv_cdf((0.5 - FALSE_ALARM) / (1 - FALSE_ALARM - LAPSE))


def clinical_reference(T: float):
    """ASHA (2005): the lowest 5-dB step responded to at least half the time."""
    mu = T - MU_OFFSET
    for level in range(MIN_DB, MAX_DB + 5, 5):
        p = FALSE_ALARM + (1 - FALSE_ALARM - LAPSE) * NormalDist(mu, SIGMA).cdf(level)
        if p >= 0.5 - 1e-9:
            return level
    return "NR"


def expected_mapping(T: int):
    """A posterior point mass at T reports the lowest 5-dB step at or above T."""
    step = math.ceil(T / 5) * 5
    return "NR" if step > MAX_DB else max(MIN_DB, step)


MAPPING_POINTS = [-30, -14, -11, -10, -9, -6, -5, 0, 1, 4, 5, 6, 12, 15,
                  44, 85, 86, 89, 90, 91, 93, 110]
DETERMINISTIC = sorted(set(AUDIT_LISTENER + [-15, -10, -5, 0, 5, 80, 85, 88, 90, 95, 200]))


@pytest.fixture(scope="module")
def simulated(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; the screening estimators are JavaScript")
    harness = tmp_path_factory.mktemp("screening") / "harness.mjs"
    harness.write_text(HARNESS, encoding="utf-8")
    cfg = {"deterministic": DETERMINISTIC, "mapping": MAPPING_POINTS,
           "noisy_n": 1200, "seed": 20261001, "mu_offset": MU_OFFSET}
    run = subprocess.run([node, str(harness), str(BAYES_JS), str(TONE_JS), json.dumps(cfg)],
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_bayesian_reads_the_deterministic_listener_exactly(simulated):
    """Every threshold on the clinical convention, none half a step too good."""
    for T in AUDIT_LISTENER:
        got = simulated["deterministic"][str(T)]
        assert got["bayes"]["threshold"] == T, (T, got["bayes"]["trials"])
        # The staircase is the reference procedure and was already exact.
        assert got["stair"]["threshold"] == T


def test_bayesian_maps_the_posterior_onto_5_db_steps(simulated):
    for T in MAPPING_POINTS:
        assert simulated["mapping"][str(T)] == expected_mapping(T), T


def test_bayesian_reports_no_response_only_after_silence_at_the_top(simulated):
    for T in (95, 200):
        run = simulated["deterministic"][str(T)]["bayes"]
        assert run["threshold"] == "NR"
        assert [MAX_DB, False] in run["trials"], "NR without a tone at the maximum"
    # Heard at the maximum level: a threshold, not NR.
    for T in (88, 90):
        assert simulated["deterministic"][str(T)]["bayes"]["threshold"] == 90


def test_bayesian_floor_rests_on_a_tone_heard_at_the_floor(simulated):
    for T in (-15, -10):
        run = simulated["deterministic"][str(T)]["bayes"]
        assert run["threshold"] == MIN_DB
        assert [MIN_DB, True] in run["trials"]


def test_bayesian_is_unbiased_against_the_clinical_threshold(simulated):
    """1,200 noisy thresholds: no systematic lean towards better hearing."""
    rows = simulated["noisy"]
    errors_b, errors_s = [], []
    for T, bayes, stair in rows:
        ref = clinical_reference(T)
        assert bayes != "NR", f"T={T} is inside the range"
        errors_b.append(bayes - ref)
        if stair != "NR":
            errors_s.append(stair - ref)
    n = len(errors_b)
    bias = sum(errors_b) / n
    mae = sum(abs(e) for e in errors_b) / n
    too_good = sum(e < 0 for e in errors_b) / n
    exact = sum(e == 0 for e in errors_b) / n
    # Rounding the posterior mean to the nearest step scores bias -2.2 dB and
    # 45% one step too good on this same population.
    assert abs(bias) <= 1.0, bias
    assert too_good <= 0.30, too_good
    assert exact >= 0.55, exact
    assert mae <= 2.3, mae
    # The staircase, scored the same way, as a sanity anchor for the reference.
    assert abs(sum(errors_s) / len(errors_s)) <= 1.0


# ------------------------------------------------------- catch trials ---

def runner_testing_block(src: str) -> str:
    start = src.index("stage === 'testing' && step")
    return src[start:src.index("stage === 'done'", start)]


def test_testing_screen_does_not_reveal_catch_trials():
    block = runner_testing_block(read(RUNNER))
    assert "isCatch" not in block
    assert "catch trial" not in block.lower()
    assert "nothing was played" not in block


def test_testing_screen_does_not_show_the_presentation_level():
    block = runner_testing_block(read(RUNNER))
    assert not re.search(r"\{\s*level\s*\}", block)
    assert "testing at" not in block


def test_silent_trial_lasts_as_long_as_a_tone():
    tone = read(TONE_JS)
    sig = re.search(r"playTone\([^)]*\{\s*pulses\s*=\s*(\d+),\s*pulseMs\s*=\s*(\d+),"
                    r"\s*gapMs\s*=\s*(\d+)\s*\}", tone)
    assert sig, "playTone's default envelope moved; re-derive the silent window"
    pulses, pulse_ms, gap_ms = map(int, sig.groups())
    lead = re.search(r"const t0 = ctx\.currentTime \+ ([\d.]+)", tone)
    tail = re.search(r"osc\.stop\(t \+ ([\d.]+)\)", tone)
    assert lead and tail
    tone_ms = 1000 * float(lead.group(1)) + pulses * (pulse_ms + gap_ms) \
        + 1000 * float(tail.group(1))

    runner = read(RUNNER)
    expr = re.search(r"const TONE_PRESENTATION_MS = ([\d\s+*()]+)\n", runner)
    assert expr
    assert eval(expr.group(1), {"__builtins__": {}}) == pytest.approx(tone_ms)  # noqa: S307
    assert "setTimeout(r, TONE_PRESENTATION_MS)" in runner


def test_staircase_run_ends_on_done_not_on_a_returned_threshold():
    """The staircase's presentation cap sets done without returning a value."""
    runner = read(RUNNER)
    assert "if (threshold === null) return" not in runner
    assert "if (!est.done) return" in runner


# ------------------------------------------------------- otoscopy atlas ---

def test_reference_images_load_in_cors_mode():
    src = read(OTOSCOPY)
    imgs = re.findall(r"<img\b[^>]*?src=\{referenceUrl\([^>]*>", src, re.S)
    assert len(imgs) >= 2
    for tag in imgs:
        assert 'crossOrigin="anonymous"' in tag, tag


def test_reference_images_never_use_the_unversioned_url():
    """A browser that cached a reference image before the API sent CORS
    headers holds it without Access-Control-Allow-Origin and, with no
    Cache-Control on the old response, treats it as fresh. The versioned URL
    is what keeps a crossOrigin <img> from being handed that copy."""
    src = read(OTOSCOPY)
    assert not re.search(r"<img\b[^>]*?src=\{apiUrl\(", src, re.S)
    assert "fetch(apiUrl(" not in src
    assert re.search(r"const REFERENCE_IMAGE_VERSION = '[^']+'", src)


def run_reference_body() -> str:
    src = read(OTOSCOPY)
    start = src.index("async function runReference")
    return src[start:src.index("\n  }\n", start)]


def test_run_reference_bypasses_the_http_cache():
    assert "fetch(referenceUrl(src), { cache: 'no-store' })" in run_reference_body()


def test_run_reference_labels_the_upload_with_its_real_type():
    body = run_reference_body()
    assert "image/png" not in body and "reference.png" not in body
    assert "new File([blob], filename, { type })" in body


@pytest.fixture
def atlas_images():
    images = [img for c in client.get("/api/otoscopy/reference").json()["classes"]
              for img in c["images"]]
    if not images:
        pytest.skip("no reference images shipped")
    return images


def test_reference_image_answers_a_cors_mode_request(atlas_images):
    """What crossOrigin="anonymous" needs from the API for the atlas to load,
    requested exactly as the page requests it — with the version parameter."""
    origin = "http://localhost:5173"
    r = client.get(atlas_images[0] + "?v=cors1", headers={"Origin": origin})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert "origin" in r.headers.get("vary", "").lower()


def test_reference_image_type_matches_its_extension(atlas_images):
    """The upload's filename is built from the served type; they must agree."""
    served = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    types = set()
    for url in atlas_images:
        r = client.get(url)
        assert r.status_code == 200
        ctype = r.headers["content-type"].split(";")[0].strip()
        assert ctype == served[url.rsplit(".", 1)[-1].lower()], url
        types.add(ctype)
    # The shipped atlas is JPEG: a fixed image/png label was wrong for it.
    assert "image/jpeg" in types


# --------------------------------------------------------- hearing age ---

def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def test_frontend_renders_no_age_comparison():
    pattern = re.compile(r"hearing[\s_-]*age|hearingAge|\.norms\b|ISO\s*7029", re.I)
    offenders = []
    for path in sorted(FRONTEND.rglob("*")):
        if path.suffix not in {".js", ".jsx", ".json"}:
            continue
        for i, line in enumerate(strip_comments(read(path)).splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert not offenders, offenders


def test_verdict_banner_drops_a_hearing_age_figure():
    src = read(VERDICT_BANNER)
    assert "verdict.numbers.map" not in src
    m = re.search(r"isAgeComparison = \(n\) => /(.+?)/i\.test", src)
    assert m, "the banner no longer filters age comparisons"
    is_age = re.compile(m.group(1), re.I)
    for label in ("Hearing age", "hearing_age", "HEARING-AGE"):
        assert is_age.search(label), label
    for label in ("Right ear PTA", "Left ear PTA", "Disability (RPwD 2016)",
                  "Speech cues audible"):
        assert not is_age.search(label), label
