"""Train the otoscopic pattern classifier.

    python -m scripts.train_otoscopy            # reference set (+ Kaggle if present)
    python -m scripts.train_otoscopy --no-cv    # skip validation, just fit

Training sources, both optional, both used when present:

    data/otoscope_reference/<class>/*.png   shipped with the repository; the
                                            labelled views extracted from the
                                            clinical team's reference document
    data/otoscope_kaggle/<class>/*.jpg      the public otoscope dataset, which
                                            is not redistributable and so is
                                            not committed here

Run ``python -m scripts.fetch_otoscope_dataset --help`` for how to put the
Kaggle data in place. Nothing else changes: the same features, the same API,
the same screens — the model card simply records a larger training set and a
better validated accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.otoscopy.model import KAGGLE_DIR, REFERENCE_DIR, train


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-cv", action="store_true",
                    help="skip leave-one-image-out validation (much faster)")
    args = ap.parse_args()

    roots = [p for p in (REFERENCE_DIR, KAGGLE_DIR) if p.exists()]
    if not roots:
        print(f"No training data. Expected {REFERENCE_DIR} to exist.")
        print("Run: python -m scripts.extract_otoscope_reference <docx>")
        return 1

    print("training sources:")
    for r in roots:
        print(f"  {r}")
    if not KAGGLE_DIR.exists():
        print(f"\n  note: {KAGGLE_DIR.name}/ absent — training on the reference "
              f"set alone.\n  See scripts/fetch_otoscope_dataset.py to add the "
              f"public dataset.")

    card = train(roots, run_cv=not args.no_cv)

    print("\nmodel card")
    print(json.dumps({k: v for k, v in card.items() if k != "validation"}, indent=2))
    val = card.get("validation", {})
    if val.get("accuracy") is not None:
        print(f"\nvalidation: {val['method']}")
        print(f"  images tested       : {val['images_tested']}")
        print(f"  chance level        : {val['chance_level']:.1%}")
        print(f"  exact class  top-1  : {val['accuracy']:.1%}")
        print(f"               top-2  : {val['top2_accuracy']:.1%}")
        print(f"               top-3  : {val['top3_accuracy']:.1%}")
        print(f"  coarse category     : {val['category_accuracy']:.1%}")
        print(f"  urgency band        : {val['urgency_accuracy']:.1%}")
        print(f"  nearest reference   : {val['retrieval_top1']:.1%} "
              f"(correct class in top 3: {val['retrieval_top3']:.1%})")
        print("  per-class recall:")
        for cls, v in val["per_class_recall"].items():
            rec = "n/a" if v["recall"] is None else f"{v['recall']:.0%}"
            print(f"    {cls:24s} {v['correct']:2d}/{v['n']:<2d}  {rec}")
    if card.get("unmapped_folders"):
        print("\nunmapped folders (not used — add them to DATASET_ALIASES):")
        for name in card["unmapped_folders"]:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
