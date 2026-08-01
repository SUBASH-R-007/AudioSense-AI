"""Put the public otoscope dataset in place, then retrain.

    python -m scripts.fetch_otoscope_dataset            # download via Kaggle API
    python -m scripts.fetch_otoscope_dataset --from DIR # use an existing copy
    python -m scripts.fetch_otoscope_dataset --check    # report what is present

The dataset is https://www.kaggle.com/datasets/omduggineni/otoscopedata.
It is not committed to this repository: it is not ours to redistribute, and
Kaggle downloads require an authenticated account. Everything in the app
works without it — the classifier trains on the reference views extracted
from the clinical team's own document — but the dataset is a few thousand
images rather than a few dozen, and it is the difference between a model that
demonstrates the pipeline and a model to deploy.

Two ways to get it:

  1. Kaggle API. `pip install kaggle`, then put your kaggle.json token at
     %USERPROFILE%\\.kaggle\\kaggle.json (Windows) or ~/.kaggle/kaggle.json,
     and run this script with no arguments.

  2. Manual. Download the ZIP from the dataset page, extract it anywhere, and
     run this script with --from <that folder>.

Either way the images are copied into data/otoscope_kaggle/<class>/ using
this project's class names, and any folder whose name does not map onto our
taxonomy is reported rather than silently guessed at. Then run:

    python -m scripts.train_otoscopy
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from app.otoscopy.model import (
    DATASET_ALIASES, IMAGE_SUFFIXES, KAGGLE_DIR, REFERENCE_DIR, _canonical,
    scan_directory,
)

SLUG = "omduggineni/otoscopedata"


def _report(root: Path, title: str) -> int:
    found, unmapped = scan_directory(root)
    total = sum(len(v) for v in found.values())
    print(f"\n{title}: {root}")
    if not root.exists():
        print("  (absent)")
        return 0
    for label in sorted(found):
        print(f"  {label:24s} {len(found[label]):5d}")
    print(f"  {'TOTAL':24s} {total:5d}")
    if unmapped:
        print("  unmapped folders (ignored):")
        for name in unmapped:
            print(f"    {name}")
        print("  -> add them to DATASET_ALIASES in app/otoscopy/model.py")
    return total


def ingest(src: Path, dest: Path = KAGGLE_DIR) -> int:
    """Copy every class folder under ``src`` into our taxonomy layout."""
    if not src.exists():
        print(f"not found: {src}")
        return 0

    # The archive may nest the class folders one or two levels down.
    candidates = [src] + [p for p in src.rglob("*") if p.is_dir()]
    best, best_score = None, 0
    for cand in candidates:
        subdirs = [p for p in cand.iterdir() if p.is_dir()] if cand.is_dir() else []
        score = sum(1 for d in subdirs if _canonical(d.name))
        if score > best_score:
            best, best_score = cand, score
    if best is None or best_score == 0:
        print(f"no recognisable class folders under {src}")
        print("expected subdirectories such as: " + ", ".join(sorted(set(DATASET_ALIASES))[:6]))
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for child in sorted(p for p in best.iterdir() if p.is_dir()):
        label = _canonical(child.name)
        if label is None:
            print(f"  skipping unmapped folder: {child.name}")
            continue
        out = dest / label
        out.mkdir(parents=True, exist_ok=True)
        for i, path in enumerate(sorted(p for p in child.rglob("*")
                                        if p.suffix.lower() in IMAGE_SUFFIXES)):
            shutil.copy2(path, out / f"{label}_{child.name[:12]}_{i:05d}{path.suffix.lower()}")
            copied += 1
    print(f"\ncopied {copied} images into {dest}")
    return copied


def download(tmp: Path) -> Path | None:
    """Fetch the archive with the Kaggle CLI, if it is installed and authorised."""
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download",
                        "-d", SLUG, "-p", str(tmp)], check=True)
    except FileNotFoundError:
        print("kaggle CLI not installed. Run: pip install kaggle")
        return None
    except subprocess.CalledProcessError as exc:
        print(f"kaggle download failed ({exc.returncode}).")
        print("Most often this means the API token is missing or the dataset "
              "terms have not been accepted on the website.")
        return None

    archives = sorted(tmp.glob("*.zip"))
    if not archives:
        print("download produced no archive")
        return None
    out = tmp / "extracted"
    with zipfile.ZipFile(archives[-1]) as zf:
        zf.extractall(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="source", help="folder containing an extracted copy")
    ap.add_argument("--check", action="store_true", help="report what is present and exit")
    args = ap.parse_args()

    if args.check:
        _report(REFERENCE_DIR, "reference set (committed)")
        n = _report(KAGGLE_DIR, "public dataset")
        print("\nnext: python -m scripts.train_otoscopy" if n else
              "\nThe app works without the public dataset; adding it improves accuracy.")
        return 0

    source = Path(args.source) if args.source else download(
        Path(__file__).resolve().parents[1] / "data" / "_kaggle_tmp")
    if source is None:
        return 1
    if not ingest(source):
        return 1
    _report(KAGGLE_DIR, "public dataset")
    print("\nnow run: python -m scripts.train_otoscopy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
