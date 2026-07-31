"""Make sure the model artifacts exist, training them only if they don't.

Free hosting tiers commonly cap memory at 512 MB. Training the calibrated
forest peaks around 400-500 MB of resident memory, which is close enough to
that ceiling to fail unpredictably during a build.

The artifacts are only ~8 MB, so the repository ships them and this script
becomes a no-op on deploy: it loads instantly, uses no build memory, and the
deployed model is byte-identical to the one that was tested. If the artifacts
are ever absent — a fresh clone that has not run training, or a deliberately
slim checkout — it trains them so the build still succeeds.

Run:  python -m scripts.ensure_model
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DATASET = DATA / "dataset.csv"
MODEL = DATA / "model_bundle.joblib"
DEEP = DATA / "deep_ensemble.joblib"


def main() -> int:
    if MODEL.exists():
        size = MODEL.stat().st_size / 1024 / 1024
        print(f"model_bundle.joblib present ({size:.1f} MB) — skipping training")
    else:
        print("model_bundle.joblib missing — training now")
        if not DATASET.exists():
            print("  generating dataset…")
            from app.ml.generate_dataset import DATA_DIR, generate
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            generate().to_csv(DATA_DIR / "dataset.csv", index=False)
        from app.ml.train import train
        result = train()
        print(f"  trained on {result['n']} rows — "
              f"hold-out accuracy {result['accuracy']:.4f}")

    if DEEP.exists():
        print("deep_ensemble.joblib present — skipping")
    else:
        # Optional: only /api/model/comparison and the deep-predict endpoint
        # need it, and both return 503 politely when it is absent.
        try:
            print("deep_ensemble.joblib missing — training (optional)")
            from app.ml.deep import train_deep
            result = train_deep()
            print(f"  trained {result['members']} networks — "
                  f"accuracy {result['accuracy']:.4f}")
        except Exception as exc:  # noqa: BLE001 - must never fail the build
            print(f"  skipped: {exc}")
            print("  /api/model/comparison will return 503; nothing else is affected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
