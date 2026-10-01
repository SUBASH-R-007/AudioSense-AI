"""Train the otoscopic pattern classifier.

    python -m scripts.train_otoscopy                  # reference set (+ Kaggle if present)
    python -m scripts.train_otoscopy --no-cv          # skip validation, just fit
    python -m scripts.train_otoscopy --evaluate-only  # re-measure, do not refit

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

Validation holds out every view cut from the same source picture, and fits
the scaler, PCA and classifier inside each fold. That figure leads the card
and the output below. The view-level figure is printed after it, labelled
optimistic, because sibling views of the test picture stay in training.

``--evaluate-only`` re-measures the shipped model's validation and rewrites
``data/otoscopy_model_card.json`` without touching the artifact. It refuses
if the reference data or the feature extractor no longer match what the
artifact was trained on.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.otoscopy.model import KAGGLE_DIR, REFERENCE_DIR, evaluate, train


def _print_validation(title: str, val: dict) -> None:
    if not val or val.get("accuracy") is None:
        print(f"\n{title}: not measured ({(val or {}).get('reason', 'skipped')})")
        return
    ci = val.get("accuracy_ci95")
    ci_src = val.get("accuracy_ci95_by_source_photograph")
    nir = val.get("no_information_rate", {})
    print(f"\n{title}")
    print(f"  {val['method']}")
    print(f"  views tested        : {val['images_tested']} "
          f"(from {val.get('source_photographs', '?')} source pictures, "
          f"{val['held_out_groups']} folds)")
    print(f"  chance level        : {val['chance_level']:.1%}")
    print(f"  exact class  top-1  : {val['accuracy']:.1%}  "
          f"({val['correct']}/{val['images_tested']})")
    if ci:
        print(f"    95% CI (Wilson, views independent) : {ci[0]:.1%} - {ci[1]:.1%}")
    if ci_src:
        print(f"    95% CI (resampling source pictures): {ci_src[0]:.1%} - {ci_src[1]:.1%}")
    print(f"               top-2  : {val['top2_accuracy']:.1%}")
    print(f"               top-3  : {val['top3_accuracy']:.1%}")
    print(f"  coarse category     : {val['category_accuracy']:.1%} "
          f"(always-commonest: {nir.get('category', float('nan')):.1%})")
    print(f"  urgency band        : {val['urgency_accuracy']:.1%} "
          f"(always-commonest: {nir.get('urgency', float('nan')):.1%})")
    print(f"  nearest reference   : {val['retrieval_top1']:.1%} "
          f"(correct class in top 3: {val['retrieval_top3']:.1%})")
    mtp = val.get("mean_top_probability", {})
    print(f"  mean top probability: right {mtp.get('when_correct')}, "
          f"wrong {mtp.get('when_wrong')}")
    print("  per-class recall:")
    for cls, v in val["per_class_recall"].items():
        rec = "n/a" if v["recall"] is None else f"{v['recall']:.0%}"
        src = v.get("source_photographs")
        src_text = f"  ({src} source pictures)" if src is not None else ""
        print(f"    {cls:24s} {v['correct']:2d}/{v['n']:<2d}  {rec}{src_text}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--no-cv", action="store_true",
                      help="skip validation (much faster)")
    mode.add_argument("--evaluate-only", action="store_true",
                      help="re-measure validation and rewrite the model card "
                           "without refitting the artifact")
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

    if args.evaluate_only:
        try:
            card = evaluate(roots)
        except (ValueError, FileNotFoundError) as exc:
            print(f"\ncannot evaluate: {exc}")
            return 1
    else:
        card = train(roots, run_cv=not args.no_cv)

    print("\nmodel card")
    print(json.dumps({k: v for k, v in card.items()
                      if k not in ("validation", "validation_optimistic")}, indent=2))
    _print_validation("validation (held out by source picture — the figure to quote)",
                      card.get("validation") or {})
    _print_validation("validation_optimistic (held out by view — NOT the model's accuracy)",
                      card.get("validation_optimistic") or {})
    if card.get("unmapped_folders"):
        print("\nunmapped folders (not used — add them to DATASET_ALIASES):")
        for name in card["unmapped_folders"]:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
