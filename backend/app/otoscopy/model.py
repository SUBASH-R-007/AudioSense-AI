"""Training and inference for otoscopic pattern recognition.

Two things matter more here than raw accuracy.

FIRST, HONEST VALIDATION. The reference set is small, and neither augmented
copies of one view nor the several views cut from one montage in the
reference document are independent observations: sibling views share the
camera, the session, the exposure and often the ear. The 62 reference views
come from 22 source pictures. Validation therefore holds out every view cut
from the test picture, with all their augmentations, and fits every
preprocessing step (the scaler included) on the training fold alone, so the
reported score is what happens on a photograph the model has genuinely never
seen. That number is far lower than a crop-level split gives, and it is the
one worth quoting; the crop-level figure is kept on the card, labelled as
optimistic, only so the two can be compared.

The classifier is NOT validated for diagnosis. Its label is reported as the
closest reference pattern, with ``reliable: false`` and the measured
held-out accuracy beside it, and its probabilities are not calibrated — on
held-out photographs it is about as confident when wrong as when right.

SECOND, RETRIEVAL BESIDE CLASSIFICATION. A label with a probability is a
claim. The three most similar labelled reference views, shown side by side
with the patient's image, are evidence — and they stay useful even when the
classifier is unsure. That is also, literally, what was asked for: match the
patient's membrane against the patterns in the reference document.

The model upgrades without any code change: drop the Kaggle otoscope dataset
into ``data/otoscope_kaggle/<class>/`` and re-run the training script. The
feature representation, the API and the UI are identical either way; only the
model card changes to record the larger training set.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.otoscopy import features as F
from app.otoscopy.taxonomy import CLASSES, TAXONOMY, describe

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REFERENCE_DIR = DATA_DIR / "otoscope_reference"
KAGGLE_DIR = DATA_DIR / "otoscope_kaggle"
ARTIFACT = DATA_DIR / "otoscopy_model.joblib"
#: The published model card. Written by ``train`` beside the artifact, and
#: rewritten by ``evaluate`` when the validation is re-measured without
#: refitting; it is served in place of the copy baked into the artifact
#: whenever both describe the same training data.
CARD_PATH = DATA_DIR / "otoscopy_model_card.json"

#: Folder names used by public otoscope datasets, mapped onto our taxonomy.
#: Unmapped folders are reported rather than guessed at — a silently
#: mislabelled class is worse than a missing one.
DATASET_ALIASES: Dict[str, str] = {
    "normal": "normal",
    "normal tympanic membrane": "normal",
    "normal eardrum": "normal",
    "earwax": "cerumen_impaction",
    "earwax plug": "cerumen_impaction",
    "cerumen": "cerumen_impaction",
    "cerumen impaction": "cerumen_impaction",
    "wax": "cerumen_impaction",
    "aom": "otitis_media",
    "acute otitis media": "otitis_media",
    "otitis media": "otitis_media",
    "otitis media with effusion": "otitis_media",
    "ome": "otitis_media",
    "effusion": "otitis_media",
    "retraction": "retraction",
    "tympanic membrane retraction": "retraction",
    "eustachian tube dysfunction": "retraction",
    "csom": "perforation_central",
    "chronic otitis media": "perforation_central",
    "chronic suppurative otitis media": "perforation_central",
    "perforation": "perforation_central",
    "central perforation": "perforation_central",
    "tympanic membrane perforation": "perforation_central",
    "marginal perforation": "perforation_marginal",
    "attic perforation": "perforation_attic",
    "attic retraction": "perforation_attic",
    "cholesteatoma": "perforation_attic",
    "tumor": "tumor",
    "tumour": "tumor",
    "mass": "tumor",
    "glomus": "tumor",
    "neoplasm": "tumor",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# --------------------------------------------------------------------------
# augmentation
# --------------------------------------------------------------------------
#: Otoscope photographs vary in rotation (how the scope was held), exposure
#: (lamp brightness and distance) and framing. Augmenting along exactly those
#: axes teaches invariance to the things that are not diagnostic, while
#: leaving the things that are — colour, texture, where a defect sits — alone.
#: Rotation is kept modest because superior/inferior position IS diagnostic
#: for attic disease.
AUG_ROTATIONS = (-18, -9, 0, 9, 18)
AUG_GAINS = (0.82, 1.0, 1.18)
AUG_FLIP = (False, True)


def augment(bgr: np.ndarray, full: bool = True) -> List[np.ndarray]:
    """Plausible re-photographs of the same ear."""
    if not full:
        return [bgr]
    h, w = bgr.shape[:2]
    centre = (w / 2.0, h / 2.0)
    out: List[np.ndarray] = []
    for angle in AUG_ROTATIONS:
        rot = bgr if angle == 0 else cv2.warpAffine(
            bgr, cv2.getRotationMatrix2D(centre, angle, 1.0), (w, h),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        for flip in AUG_FLIP:
            # A left ear is the mirror image of a right ear, so horizontal
            # flips are real variation, not synthetic noise.
            img = cv2.flip(rot, 1) if flip else rot
            for gain in AUG_GAINS:
                out.append(img if gain == 1.0 else
                           np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8))
    return out


# --------------------------------------------------------------------------
# dataset loading
# --------------------------------------------------------------------------
def _canonical(folder: str) -> Optional[str]:
    key = folder.strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in DATASET_ALIASES:
        return DATASET_ALIASES[key]
    compact = key.replace(" ", "_")
    return compact if compact in TAXONOMY else None


def scan_directory(root: Path) -> Tuple[Dict[str, List[Path]], List[str]]:
    """Class folders under ``root``, plus the folder names we refused to map."""
    found: Dict[str, List[Path]] = {}
    unmapped: List[str] = []
    if not root.exists():
        return found, unmapped
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        label = _canonical(child.name)
        paths = sorted(p for p in child.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
        if not paths:
            continue
        if label is None:
            unmapped.append(child.name)
            continue
        found.setdefault(label, []).extend(paths)
    return found, unmapped


def load_dataset(
    roots: Sequence[Path], augmented: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Path], List[str]]:
    """Feature matrix, labels, grouping key and source paths.

    The grouping key is the image file — one reference view. Every
    augmentation of one view carries the same key, so validation can hold all
    of them out together and score the view once. Views cut from the same
    source picture carry different keys here; ``source_groups`` maps each row
    to that picture, which is the unit validation must hold out.
    """
    X: List[np.ndarray] = []
    y: List[str] = []
    groups: List[int] = []
    paths: List[Path] = []
    unmapped_all: List[str] = []
    group_id = 0

    for root in roots:
        found, unmapped = scan_directory(Path(root))
        unmapped_all.extend(unmapped)
        for label in sorted(found):
            for path in found[label]:
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                for variant in augment(image, full=augmented):
                    vec, _ = F.extract(variant)
                    X.append(vec)
                    y.append(label)
                    groups.append(group_id)
                    paths.append(path)
                group_id += 1

    if not X:
        return (np.empty((0, len(F.FEATURE_NAMES)), np.float32),
                np.array([]), np.array([]), [], unmapped_all)
    return (np.vstack(X), np.asarray(y), np.asarray(groups), paths,
            sorted(set(unmapped_all)))


#: ``extract_otoscope_reference.py`` names each panel it cuts out of a
#: montage ``<class>_<digest>_<NN>``, where ``<digest>`` (eight hex digits of
#: the MD5 of the embedded picture) identifies the picture it came from.
_SOURCE_DIGEST = re.compile(r"_([0-9a-f]{8})_\d{2,}$")


def source_photograph(path) -> str:
    """The source picture a reference view was cut from.

    Panels of one montage share a camera, a session, an exposure and often
    the ear itself, so for validation they are one observation, not several.
    A file that does not follow the extraction script's naming — a public
    dataset image — is treated as its own source.
    """
    p = Path(str(path))
    match = _SOURCE_DIGEST.search(p.stem)
    return match.group(1) if match else p.as_posix()


def source_groups(paths: Sequence) -> np.ndarray:
    """Integer source-picture id per row, for ``LeaveOneGroupOut``."""
    keys = np.asarray([source_photograph(p) for p in paths])
    return np.unique(keys, return_inverse=True)[1]


def training_fingerprint(ref_paths: Sequence, ref_y: Sequence) -> str:
    """Identity of a training set: which files, under which labels.

    Ties a published model card to the artifact it describes. Path
    separators are normalised so the same data fingerprints the same on
    Windows and in the Linux container.
    """
    items = sorted(f"{lbl}|{str(p).replace(chr(92), '/')}"
                   for p, lbl in zip(ref_paths, ref_y))
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------
def _make_classifier():
    """PCA then multinomial logistic regression.

    Chosen over random forests, extra trees and an RBF SVM in a comparison
    run with one reference view held out at a time — a protocol that leaves
    sibling views of the test picture in training, so the comparison favoured
    whichever model memorised montages best and has not been repeated with
    whole source pictures held out. With 391 correlated descriptors and 62
    views from 22 source pictures, the projection to 20 components is what
    keeps the model from fitting the noise. Measured figures live only in the
    model card, which the training and evaluation scripts regenerate.
    """
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        PCA(n_components=20, random_state=0),
        LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"),
    )


#: Thresholds on the model's own averaged probabilities. They describe how
#: far the top class separates from the rest, NOT how likely it is to be
#: right: on held-out source pictures the top probability is about as high
#: when the answer is wrong as when it is right. The card records the
#: held-out accuracy inside each band so that can be checked, and no
#: calibration is fitted — 22 source pictures cannot validate one.
PROBABLE_MIN_CONFIDENCE = 0.55
PROBABLE_MIN_MARGIN = 0.18
PROVISIONAL_MIN_CONFIDENCE = 0.38


def _probability_band(confidence: float, margin: float) -> str:
    if confidence >= PROBABLE_MIN_CONFIDENCE and margin >= PROBABLE_MIN_MARGIN:
        return "probable"
    if confidence >= PROVISIONAL_MIN_CONFIDENCE:
        return "provisional"
    return "uncertain"


def wilson_interval(k: int, n: int, z: float = 1.959964) -> Optional[List[float]]:
    """95% Wilson score interval for ``k`` successes in ``n`` trials.

    Wilson EB (1927). Probable inference, the law of succession, and
    statistical inference. J Am Stat Assoc 22:209-212. Used instead of the
    normal approximation because it stays inside [0, 1] and keeps its
    coverage at the small counts this reference set produces.
    """
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def _cluster_bootstrap_interval(correct: Sequence, clusters: Sequence,
                                n_boot: int = 2000,
                                seed: int = 0) -> Optional[List[float]]:
    """95% percentile interval for accuracy, resampling whole source pictures.

    Views cut from one picture are correlated, so an interval that treats
    them as independent (Wilson, above) is too narrow. Resampling clusters
    rather than individual views is the standard remedy for hierarchical
    data: Davison AC, Hinkley DV (1997), Bootstrap Methods and their
    Application, section 3.8; Field CA, Welsh AH (2007), Bootstrapping
    clustered data, J R Stat Soc B 69:369-390. Seeded so the card is
    reproducible.
    """
    correct = np.asarray(correct, dtype=float)
    clusters = np.asarray(clusters)
    ids = np.unique(clusters)
    if len(ids) < 2:
        return None
    hits = np.array([correct[clusters == c].sum() for c in ids])
    sizes = np.array([(clusters == c).sum() for c in ids], dtype=float)
    draws = np.random.default_rng(seed).integers(0, len(ids), size=(n_boot, len(ids)))
    accuracy = hits[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    lo, hi = np.percentile(accuracy, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


#: How each validation protocol is described on the card.
PROTOCOLS: Dict[str, str] = {
    "source_photograph": (
        "leave-one-source-photograph-out: every view cut from the held-out "
        "picture, with all its augmentations, is removed from training; the "
        "scaler, PCA and classifier are fit on the training fold alone; each "
        "held-out view is scored once, with probabilities averaged over its "
        "augmentations"),
    "crop": (
        "leave-one-view-out (OPTIMISTIC): one view and its augmentations are "
        "held out while sibling views cut from the same source picture stay "
        "in training, so the model is partly tested on a picture it learned "
        "from; kept only for comparison with the source-photograph figure"),
}


def _grouped_cv(X: np.ndarray, y: np.ndarray, crops: np.ndarray,
                folds: np.ndarray, protocol: str,
                sources: Optional[np.ndarray] = None) -> dict:
    """Held-out accuracy at three levels of granularity.

    ``folds`` decides what is held out together; ``crops`` decides what is
    scored as one test case. With ``folds`` set to the source picture
    (``source_groups``) no view of the test picture, and no augmentation of
    one, is ever in training. Every fitted step, the feature scaler
    included, is fit inside the fold: a scaler fit on all rows has already
    seen the test picture's feature distribution. ``sources`` (the source
    picture per row) adds per-class source counts and an interval that
    resamples whole pictures.

    Three levels are scored because they are not equally learnable and they
    are not equally important. Which of three perforation sites this is:
    hard. Whether there is a perforation at all: easier in principle.
    Whether this ear needs an urgent referral: the one a triage decision
    rests on. Each is reported beside its no-information rate — the score of
    always answering the commonest label — because a coarse level with a few
    unbalanced bands can look accurate while knowing nothing.
    """
    from sklearn.model_selection import LeaveOneGroupOut
    from sklearn.preprocessing import StandardScaler

    from app.otoscopy.taxonomy import CATEGORY, URGENCY

    if len(np.unique(folds)) < 3:
        return {"method": "none", "protocol": protocol,
                "reason": "fewer than three held-out groups"}

    cases: List[dict] = []
    for train_idx, test_idx in LeaveOneGroupOut().split(X, y, folds):
        if len(np.unique(y[train_idx])) < 2:
            continue
        scaler = StandardScaler().fit(X[train_idx])
        X_train = scaler.transform(X[train_idx])
        X_test = scaler.transform(X[test_idx])
        clf = _make_classifier()
        clf.fit(X_train, y[train_idx])
        classes = np.asarray(clf.classes_)
        train_crops, train_y = crops[train_idx], y[train_idx]
        test_crops, test_y = crops[test_idx], y[test_idx]

        for crop in np.unique(test_crops):
            rows = test_crops == crop
            # Average probabilities over the held-out view's augmentations,
            # which is exactly how inference works in production.
            probs = clf.predict_proba(X_test[rows]).mean(axis=0)
            order = np.argsort(probs)[::-1]
            ranked = [str(c) for c in classes[order]]
            confidence = float(probs[order[0]])
            runner_up = float(probs[order[1]]) if len(order) > 1 else 0.0

            # Retrieval is scored on the same folds: does the nearest
            # labelled view (one per training view) carry the right label?
            query = X_test[rows].mean(axis=0)
            dist = np.linalg.norm(X_train - query, axis=1)
            seen, neighbours = set(), []
            for i in np.argsort(dist):
                if train_crops[i] in seen:
                    continue
                seen.add(train_crops[i])
                neighbours.append(str(train_y[i]))
                if len(neighbours) >= 3:
                    break

            cases.append({
                "truth": str(test_y[rows][0]),
                "ranked": ranked,
                "confidence": confidence,
                "band": _probability_band(confidence, confidence - runner_up),
                "neighbours": neighbours,
                "source": (int(sources[test_idx][rows][0])
                           if sources is not None else None),
            })

    if not cases:
        return {"method": "none", "protocol": protocol, "reason": "no usable folds"}

    n = len(cases)
    truth = [c["truth"] for c in cases]
    right = np.array([c["ranked"][0] == c["truth"] for c in cases])
    k1 = int(right.sum())
    k2 = sum(c["truth"] in c["ranked"][:2] for c in cases)
    k3 = sum(c["truth"] in c["ranked"][:3] for c in cases)
    k_cat = sum(CATEGORY.get(c["ranked"][0]) == CATEGORY.get(c["truth"]) for c in cases)
    k_urg = sum(URGENCY.get(c["ranked"][0]) == URGENCY.get(c["truth"]) for c in cases)
    k_ret1 = sum(bool(c["neighbours"]) and c["neighbours"][0] == c["truth"] for c in cases)
    k_ret3 = sum(c["truth"] in c["neighbours"] for c in cases)

    def no_information(mapping: Optional[Dict[str, str]] = None) -> float:
        labels = [mapping.get(t) if mapping else t for t in truth]
        return round(max(labels.count(v) for v in set(labels)) / n, 4)

    per_class: Dict[str, dict] = {}
    confusion: Dict[str, Dict[str, int]] = {}
    for c in cases:
        confusion.setdefault(c["truth"], {}).setdefault(c["ranked"][0], 0)
        confusion[c["truth"]][c["ranked"][0]] += 1
    for cls in sorted(set(truth)):
        mine = [c for c in cases if c["truth"] == cls]
        hit = sum(c["ranked"][0] == cls for c in mine)
        entry = {"correct": hit, "n": len(mine),
                 "recall": round(hit / len(mine), 3) if mine else None}
        if sources is not None:
            entry["source_photographs"] = len({c["source"] for c in mine})
        per_class[cls] = entry

    by_band: Dict[str, dict] = {}
    for band in ("probable", "provisional", "uncertain"):
        mine = [c for c in cases if c["band"] == band]
        if mine:
            hit = sum(c["ranked"][0] == c["truth"] for c in mine)
            by_band[band] = {"correct": hit, "n": len(mine),
                             "accuracy": round(hit / len(mine), 3)}

    conf = np.array([c["confidence"] for c in cases])
    out = {
        "protocol": protocol,
        "method": PROTOCOLS[protocol],
        "optimistic": protocol != "source_photograph",
        "scaler": "fit on the training fold only",
        "held_out_groups": int(len(np.unique(folds))),
        "images_tested": n,
        "correct": k1,
        "accuracy": round(k1 / n, 4),
        "accuracy_ci95": wilson_interval(k1, n),
        "accuracy_ci95_method": (
            "Wilson score interval over views. It treats views as independent, "
            "which views cut from one picture are not, so it is too narrow."),
        "top2_accuracy": round(k2 / n, 4),
        "top3_accuracy": round(k3 / n, 4),
        "top3_ci95": wilson_interval(k3, n),
        "category_accuracy": round(k_cat / n, 4),
        "urgency_accuracy": round(k_urg / n, 4),
        "urgency_ci95": wilson_interval(k_urg, n),
        "retrieval_top1": round(k_ret1 / n, 4),
        "retrieval_top3": round(k_ret3 / n, 4),
        "chance_level": round(1.0 / max(len(np.unique(y)), 1), 4),
        "no_information_rate": {
            "exact_class": no_information(),
            "category": no_information(CATEGORY),
            "urgency": no_information(URGENCY),
        },
        "mean_top_probability": {
            "when_correct": round(float(conf[right].mean()), 3) if right.any() else None,
            "when_wrong": round(float(conf[~right].mean()), 3) if (~right).any() else None,
        },
        "accuracy_by_certainty": by_band,
        "per_class_recall": per_class,
        "confusion": confusion,
    }
    if sources is not None:
        case_sources = [c["source"] for c in cases]
        out["source_photographs"] = len(set(case_sources))
        out["accuracy_ci95_by_source_photograph"] = _cluster_bootstrap_interval(
            right, case_sources)
    return out


def reliability_note(card: Optional[dict]) -> str:
    """Plain statement that the label is not validated, with the evidence.

    Built from the card at the time it is shown, so the figures quoted are
    always the ones measured and cannot drift out of date in a string.
    """
    v = (card or {}).get("validation") or {}
    lead = ("Not a validated diagnosis: the label is the closest reference "
            "pattern, offered for comparison with the reference views.")
    if v.get("protocol") != "source_photograph" or v.get("accuracy") is None:
        return (lead + " Its accuracy on photographs it has not seen has not "
                "been measured for this model. Decide from what you see down "
                "the scope.")

    # e.g. "17 of 62 views (27%, 95% CI 15%-42%; chance 12.5%)"
    ci = v.get("accuracy_ci95_by_source_photograph") or v.get("accuracy_ci95")
    rate = f"{v['accuracy']:.0%}" + (f", 95% CI {ci[0]:.0%}-{ci[1]:.0%}" if ci else "")
    chance = (f"; chance {v['chance_level'] * 100:g}%"
              if v.get("chance_level") is not None else "")
    if v.get("correct") is not None and v.get("images_tested"):
        counted = f"{v['correct']} of {v['images_tested']} views ({rate}{chance})"
    else:
        bounds = (f"95% CI {ci[0]:.0%}-{ci[1]:.0%}" if ci else "") + chance
        counted = (f"{v['accuracy']:.0%} of held-out views"
                   + (f" ({bounds.lstrip('; ')})" if bounds else ""))
    text = (f"{lead} With every view of the test photograph held out of "
            f"training, it named the labelled pattern for {counted}")
    if v.get("top3_accuracy") is not None:
        text += f" and had it in its top three {v['top3_accuracy']:.0%} of the time"
    text += "."
    nir = (v.get("no_information_rate") or {}).get("urgency")
    if v.get("urgency_accuracy") is not None and nir is not None:
        text += (f" The urgency band was right {v['urgency_accuracy']:.0%} of "
                 f"the time, against {nir:.0%} for always answering the "
                 f"commonest band.")
    wrong = (v.get("mean_top_probability") or {}).get("when_wrong")
    if wrong is not None:
        text += (f" Its top probability averaged {wrong:.0%} even when it was "
                 "wrong, so the percentage beside a pattern is not the chance "
                 "that it is right.")
    separated = (v.get("accuracy_by_certainty") or {}).get("probable")
    if separated and separated.get("n"):
        text += (f" Even where its top pattern stood well clear of the rest "
                 f"('probable'), it was right for {separated['correct']} of "
                 f"{separated['n']} views.")
    missed = []
    for cls, r in (v.get("per_class_recall") or {}).items():
        if r.get("n") and r.get("recall") is not None and r["recall"] < 0.25:
            name = re.sub(r"\s*\([^)]*\)", "", TAXONOMY.get(cls, {}).get("name", cls))
            missed.append(f"{name.lower()} ({r['correct']}/{r['n']})")
    if missed:
        listed = (missed[0] if len(missed) == 1
                  else ", ".join(missed[:-1]) + " and " + missed[-1])
        text += (f" On unseen photographs it rarely or never identified "
                 f"{listed}, so a result that does not name them does not "
                 f"exclude them.")
    return text + " Decide from what you see down the scope."


def _default_roots() -> List[Path]:
    return [p for p in (REFERENCE_DIR, KAGGLE_DIR) if p.exists()]


def _validate(X: np.ndarray, y: np.ndarray, crops: np.ndarray,
              paths: Sequence) -> Tuple[dict, dict]:
    """(source-photograph validation, optimistic view-level validation).

    The first is the model's accuracy. The second exists only so the gap
    between the two protocols stays visible on the card.
    """
    sources = source_groups(paths)
    return (_grouped_cv(X, y, crops, sources, "source_photograph", sources),
            _grouped_cv(X, y, crops, crops, "crop", sources))


def _unique_views(paths: Sequence, y: Sequence) -> Tuple[List[str], List[str]]:
    """One (path relative to data/, label) per view, in load order."""
    seen = dict.fromkeys((str(Path(p).relative_to(DATA_DIR)), str(lbl))
                         for p, lbl in zip(paths, y))
    return [p for p, _ in seen], [lbl for _, lbl in seen]


def _build_card(X: np.ndarray, y: np.ndarray, roots: Sequence[Path],
                unmapped: List[str], view_paths: List[str], view_y: List[str],
                validation: dict, optimistic: Optional[dict],
                novelty_cut: float) -> dict:
    """The model card, leading with what a reader most needs to know.

    ``reliable`` is fixed at False. Cross-validation on a reference atlas
    can show a model is NOT ready; it cannot show that it is. Clearing it
    needs an external, prospective validation on consecutive clinic
    photographs, which is a clinical-governance decision, not a training
    output.
    """
    sources = {}
    for root in roots:
        found, _ = scan_directory(Path(root))
        sources[Path(root).name] = {k: len(v) for k, v in sorted(found.items())}

    card = {
        "classes": sorted(set(y.tolist())),
        "reliable": False,
        "reliability_note": "",
        "validation": validation,
        "validation_optimistic": optimistic,
        "n_images": int(len(view_paths)),
        "n_source_photographs": int(len({source_photograph(p) for p in view_paths})),
        "n_training_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "augmentations_per_image": len(AUG_ROTATIONS) * len(AUG_GAINS) * len(AUG_FLIP),
        "sources": sources,
        "unmapped_folders": unmapped,
        "kaggle_present": KAGGLE_DIR.exists(),
        "novelty_threshold": round(novelty_cut, 3),
        "training_fingerprint": training_fingerprint(view_paths, view_y),
    }
    card["reliability_note"] = reliability_note(card)
    return card


def train(
    roots: Optional[Sequence[Path]] = None,
    out_path: Path = ARTIFACT,
    run_cv: bool = True,
    card_path: Path = CARD_PATH,
) -> dict:
    """Fit the classifier and write the artifact. Returns the model card."""
    import joblib
    from sklearn.preprocessing import StandardScaler

    roots = list(roots) if roots else _default_roots()
    X, y, crops, paths, unmapped = load_dataset(roots)
    if X.shape[0] == 0:
        raise FileNotFoundError(
            f"no otoscope images found under {[str(r) for r in roots]}")

    # Validation refits every step inside each fold from the raw features,
    # so it never sees the scaler fitted below on all rows.
    if run_cv:
        validation, optimistic = _validate(X, y, crops, paths)
    else:
        validation, optimistic = {"method": "skipped"}, None

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    clf = _make_classifier()
    clf.fit(Xs, y)

    # Retrieval bank: one un-augmented descriptor per reference image, so
    # "most similar reference view" points at a real file we can display.
    ref_X, ref_y, _, ref_paths, _ = load_dataset(roots, augmented=False)
    ref_Xs = scaler.transform(ref_X) if len(ref_X) else ref_X
    ref_rel = [str(Path(p).relative_to(DATA_DIR)) for p in ref_paths]

    # Novelty threshold: how far a genuine otoscope image sits from its
    # nearest training neighbour. Anything well beyond this is not an ear.
    nn_dists = []
    for i in range(0, len(Xs), max(1, len(Xs) // 400)):
        d = np.linalg.norm(ref_Xs - Xs[i], axis=1) if len(ref_Xs) else np.array([0.0])
        nn_dists.append(float(d.min()))
    novelty_cut = float(np.percentile(nn_dists, 99)) if nn_dists else 0.0

    card = _build_card(X, y, roots, unmapped, ref_rel,
                       [str(v) for v in ref_y], validation, optimistic,
                       novelty_cut)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "clf": clf, "scaler": scaler, "feature_names": F.FEATURE_NAMES,
        "ref_X": ref_Xs, "ref_y": ref_y, "ref_paths": ref_rel,
        "novelty_cut": novelty_cut, "card": card,
    }, out_path)
    card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    _reset_bundle()
    return card


def evaluate(
    roots: Optional[Sequence[Path]] = None,
    artifact: Path = ARTIFACT,
    card_path: Path = CARD_PATH,
) -> dict:
    """Re-measure the shipped model's validation and republish its card.

    Refits nothing and leaves the artifact untouched. What is measured is
    the training procedure on the same data — the procedure that produced
    the artifact — so the card remains a description of the shipped model.
    Refuses when the data on disk is not the data the artifact was trained
    on, or the features no longer match: that needs ``train``, not a card.
    """
    import joblib

    roots = list(roots) if roots else _default_roots()
    bundle = joblib.load(artifact)
    X, y, crops, paths, unmapped = load_dataset(roots)
    if X.shape[0] == 0:
        raise FileNotFoundError(
            f"no otoscope images found under {[str(r) for r in roots]}")

    view_paths, view_y = _unique_views(paths, y)
    shipped = training_fingerprint(bundle.get("ref_paths", []), bundle.get("ref_y", []))
    if training_fingerprint(view_paths, view_y) != shipped:
        raise ValueError("the reference data on disk is not what the shipped "
                         "artifact was trained on — retrain instead")
    if X.shape[1] != len(bundle.get("feature_names", [])):
        raise ValueError("the feature extractor has changed since the artifact "
                         "was trained — retrain instead")

    validation, optimistic = _validate(X, y, crops, paths)
    card = _build_card(X, y, roots, unmapped, view_paths, view_y,
                       validation, optimistic, float(bundle.get("novelty_cut", 0.0)))
    card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    _reset_bundle()
    return card


# --------------------------------------------------------------------------
# inference
# --------------------------------------------------------------------------
_BUNDLE: Optional[dict] = None


def model_available() -> bool:
    return ARTIFACT.exists()


def _reset_bundle() -> None:
    global _BUNDLE
    _BUNDLE = None


def _published_card(bundle: dict, card_path: Optional[Path] = None) -> dict:
    """The card to serve for a loaded artifact.

    The published JSON card is served when it describes the same training
    data as the artifact, which is how a re-measured validation reaches the
    API without refitting the model. Otherwise the card baked into the
    artifact is served — and if that card predates source-photograph
    validation, its view-level figures are moved to ``validation_optimistic``
    and ``validation`` is left empty, so nothing downstream quotes them as
    the model's accuracy.
    """
    card_path = CARD_PATH if card_path is None else card_path
    fingerprint = training_fingerprint(bundle.get("ref_paths", []),
                                       bundle.get("ref_y", []))
    try:
        published = json.loads(Path(card_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        published = None
    if (isinstance(published, dict)
            and published.get("training_fingerprint") == fingerprint):
        published["reliable"] = False
        published["reliability_note"] = reliability_note(published)
        return published

    card = dict(bundle.get("card") or {})
    validation = card.get("validation")
    if not (isinstance(validation, dict)
            and validation.get("protocol") == "source_photograph"):
        if isinstance(validation, dict) and validation.get("accuracy") is not None:
            card["validation_optimistic"] = {
                **validation, "protocol": "crop", "optimistic": True,
                "method": PROTOCOLS["crop"] + "; scaler fit on all rows before "
                          "cross-validation",
            }
        card["validation"] = None
    card["training_fingerprint"] = fingerprint
    card["reliable"] = False
    card["reliability_note"] = reliability_note(card)
    return card


def load_bundle() -> dict:
    global _BUNDLE
    if _BUNDLE is None:
        if not ARTIFACT.exists():
            raise FileNotFoundError(
                "otoscopy model not trained — run: python -m scripts.train_otoscopy")
        import joblib
        bundle = joblib.load(ARTIFACT)
        bundle["card"] = _published_card(bundle)
        _BUNDLE = bundle
    return _BUNDLE


def model_card() -> dict:
    try:
        return load_bundle()["card"]
    except FileNotFoundError:
        return {"trained": False}


def _evidence(named: Dict[str, float], label: str) -> List[str]:
    """Plain-language reasons, drawn from the measured descriptors.

    These are not post-hoc rationalisations of the model's output: each line
    quotes a number the classifier actually saw, so a clinician who disagrees
    can point at the specific measurement that is wrong.
    """
    out: List[str] = []
    red = named.get("erythema", 0.0)
    wax = named.get("wax_fraction", 0.0)
    cone = named.get("cone_of_light", 0.0)
    defect = named.get("defect_size", 0.0)
    superior = named.get("defect_superior", 0.0)
    offset = named.get("defect_offset", 0.0)
    structure = named.get("structure_visible", 0.0)

    if red > 0.20:
        out.append(f"Marked erythema over {red * 100:.0f}% of the visible membrane.")
    elif red > 0.08:
        out.append(f"Mild vascular injection ({red * 100:.0f}% of the field).")
    if wax > 0.25:
        out.append(f"Brown occluding material fills {wax * 100:.0f}% of the view — "
                   "the drum cannot be fully assessed.")
    if cone > 0.010:
        out.append("A discrete light reflex is present, which favours an intact, "
                   "normally-tensioned membrane.")
    else:
        out.append("No clear cone of light — the reflex is absent, displaced or "
                   "obscured.")
    if defect > 0.02:
        where = ("superior (pars flaccida / attic)" if superior > 0.18
                 else "peripheral, reaching the annulus" if offset > 0.55
                 else "central")
        out.append(f"A dark defect covering {defect * 100:.0f}% of the field, "
                   f"positioned {where}.")
    if structure < 0.02:
        out.append("The membrane appears opaque — middle-ear landmarks are not "
                   "visible through it.")

    entry = TAXONOMY.get(label)
    if entry:
        out.append(f"Reference description for this pattern: {entry['appearance']}")
    return out


def _similar_references(vec_scaled: np.ndarray, bundle: dict, k: int = 3) -> List[dict]:
    ref_X, ref_y, ref_paths = bundle["ref_X"], bundle["ref_y"], bundle["ref_paths"]
    if len(ref_X) == 0:
        return []
    d = np.linalg.norm(ref_X - vec_scaled, axis=1)
    order = np.argsort(d)[:k]
    span = float(d.max() - d.min()) or 1.0
    return [{
        "label": str(ref_y[i]),
        "name": TAXONOMY.get(str(ref_y[i]), {}).get("name", str(ref_y[i])),
        "similarity": round(float(1.0 - (d[i] - d.min()) / span), 3),
        "distance": round(float(d[i]), 3),
        "image": reference_url(ref_paths[i]),
    } for i in order]


def reference_url(relative_path: str) -> str:
    """Path inside data/ to the URL that serves it."""
    parts = Path(str(relative_path).replace("\\", "/")).parts
    return f"/api/otoscopy/image/{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else ""


def predict(image_bgr: np.ndarray) -> dict:
    """Read one otoscope image: ranked differential, evidence, references.

    Deliberately NOT phrased as a diagnosis. On photographs it has not seen,
    the top label is wrong more often than it is right, so the leading class
    is reported as the closest reference pattern, the result carries
    ``reliable: false``, and ``reliability_note`` quotes the measured
    held-out accuracy from the model card — the only place the figures are
    kept, so they cannot drift out of date in code. The coarse category and
    urgency band are rolled up from the same probabilities and inherit the
    same lack of validation.
    """
    from app.otoscopy.taxonomy import (
        CATEGORY, CATEGORY_LABEL, URGENCY, URGENCY_LABEL,
    )

    bundle = load_bundle()
    quality = F.image_quality(image_bgr)

    # Average the probabilities over augmentations of the query image. A view
    # whose label flips when you rotate it 9 degrees was never a confident
    # call, and averaging exposes that instead of hiding it.
    variants = augment(image_bgr, full=True)[::3]
    vectors = np.vstack([F.extract(v)[0] for v in variants])
    vec_raw, named = F.extract(image_bgr)

    scaler, clf = bundle["scaler"], bundle["clf"]
    probs = clf.predict_proba(scaler.transform(vectors)).mean(axis=0)
    classes = [str(c) for c in clf.classes_]
    order = np.argsort(probs)[::-1]

    top = classes[order[0]]
    confidence = float(probs[order[0]])
    runner_up = float(probs[order[1]]) if len(order) > 1 else 0.0

    vec_scaled = scaler.transform(vec_raw.reshape(1, -1))[0]
    matches = _similar_references(vec_scaled, bundle)
    nearest = matches[0]["distance"] if matches else 0.0
    novel = nearest > bundle.get("novelty_cut", 1e9) * 1.6

    # Reference views double as demo inputs, and the model has seen every one
    # of them. A near-zero distance means we are looking at a training image,
    # where the confidence is memorisation rather than generalisation. Saying
    # so is the difference between a demo and a misleading one.
    memorised = nearest < 1e-6

    ranked = [{
        "label": classes[i],
        "name": TAXONOMY.get(classes[i], {}).get("name", classes[i]),
        "probability": round(float(probs[i]), 4),
        "category": CATEGORY.get(classes[i]),
        "urgency": URGENCY.get(classes[i]),
    } for i in order]

    # Roll the class probabilities up to the coarser levels. They are
    # measured separately, and their held-out accuracy, beside the score of
    # always answering the commonest band, is on the model card
    # (validation.category_accuracy, validation.urgency_accuracy,
    # validation.no_information_rate). Read them there, not here.
    def _rollup(mapping: Dict[str, str]) -> List[dict]:
        totals: Dict[str, float] = {}
        for cls, p in zip(classes, probs):
            totals[mapping[cls]] = totals.get(mapping[cls], 0.0) + float(p)
        return sorted(({"key": k, "probability": round(v, 4)}
                       for k, v in totals.items()),
                      key=lambda d: -d["probability"])

    categories = _rollup(CATEGORY)
    urgencies = _rollup(URGENCY)

    # The band says how far the top class separates from the rest and
    # whether the image is readable at all. It is not a likelihood of being
    # right (see the thresholds above), and a well separated top class is
    # still an unvalidated one.
    margin = confidence - runner_up
    if not quality["usable"]:
        certainty = "unreliable"
    elif novel:
        certainty = "out-of-distribution"
    else:
        certainty = _probability_band(confidence, margin)

    card = bundle["card"]
    name = TAXONOMY.get(top, {}).get("name", top)
    note = reliability_note(card)

    return {
        # Fixed False: the classifier has not been validated for diagnosis
        # (see ``_build_card``), and every consumer of this result — the
        # report, the linkage, the dashboard — should see that without
        # having to read the model card.
        "reliable": False,
        "reliability_note": note,
        "prediction": {
            "label": top,
            "name": name,
            "kind": "closest_reference_pattern",
            "statement": (f"Closest reference pattern: {name}. "
                          "Not a validated diagnosis."),
            "reliable": False,
            "confidence": round(confidence, 4),
            "margin": round(margin, 4),
            "certainty": certainty,
            # How often views given this band were right with their source
            # picture held out — the band's measured meaning, from the card.
            "certainty_held_out": ((card.get("validation") or {})
                                   .get("accuracy_by_certainty") or {}).get(certainty),
        },
        "differential": ranked[:3],
        "ranked": ranked,
        "category": {
            "key": categories[0]["key"],
            "name": CATEGORY_LABEL.get(categories[0]["key"], categories[0]["key"]),
            "probability": categories[0]["probability"],
            "ranked": [{**c, "name": CATEGORY_LABEL.get(c["key"], c["key"])}
                       for c in categories],
        },
        "urgency": {
            "key": urgencies[0]["key"],
            "name": URGENCY_LABEL.get(urgencies[0]["key"], urgencies[0]["key"]),
            "probability": urgencies[0]["probability"],
            "ranked": [{**u, "name": URGENCY_LABEL.get(u["key"], u["key"])}
                       for u in urgencies],
        },
        "measurements": named,
        "evidence": _evidence(named, top),
        "reference_matches": matches,
        "quality": quality,
        "out_of_distribution": bool(novel),
        "in_training_set": bool(memorised),
        "training_set_note": (
            "This image is one of the model's own training views, so the "
            "confidence shown reflects memorisation, not performance on an "
            "unseen ear. Upload a fresh capture to see the real behaviour."
            if memorised else None
        ),
        "clinical": describe(top),
        "model": card,
        "disclaimer": (
            "Closest reference pattern, not a diagnosis. The model is trained "
            "on a small reference set and has not been validated for "
            "diagnosis; it ranks the reference patterns this image most "
            "resembles so you can compare them against what you see down the "
            "scope. It cannot exclude disease behind an obscured or partially "
            "visible membrane."
        ),
    }


# --------------------------------------------------------------------------
# clinician override
# --------------------------------------------------------------------------
def apply_correction(result: dict, corrected_label: str, *,
                     note: str = "") -> dict:
    """Replace the model's pattern with the one the clinician actually saw.

    THIS IS THE AUTHORITATIVE READING, and the rest of the system has to treat
    it that way. Measured top-1 accuracy on unseen photographs is 27%, so for
    roughly three images in four the person holding the scope is right and the
    classifier is wrong. A correction that only annotated the display would
    leave every downstream inference — the concordance against the
    tympanogram, the disease differential, the anatomy video, the report —
    still reasoning from a pattern the clinician has explicitly rejected.

    So the correction is applied where every consumer already looks:
    ``prediction.label`` and ``prediction.name``. ``linkage.py``,
    ``anatomy_video.py`` and ``concordance`` below all read those two fields,
    which means they follow the correction without knowing it happened.

    What changes:

    - ``prediction`` names the corrected pattern, with ``kind`` set to
      ``clinician_confirmed`` and NO confidence. A number there would be the
      model's score for a class the model did not choose, which is
      meaningless, and a fabricated 100% would be worse.
    - ``reliable`` becomes True — not because the model improved, but because
      the source of the label is now a clinician's direct examination. The
      note says exactly that, so nothing reads it as a validated model output.
    - ``category``, ``urgency``, ``clinical`` and ``evidence`` are recomputed
      from the corrected label: these are deterministic taxonomy lookups, so
      they are as certain as the clinician's reading.
    - ``ranked`` keeps the model's own probabilities, untouched and flagged.
      They are the record of what the model said and are needed to measure how
      often it is overridden; they just stop driving anything.

    The measurements, image quality and reference matches are left alone —
    they describe the picture, and the picture has not changed.
    """
    from app.otoscopy.taxonomy import (
        CATEGORY, CATEGORY_LABEL, URGENCY, URGENCY_LABEL,
    )

    if corrected_label not in TAXONOMY:
        raise ValueError(f"unknown otoscopic pattern: {corrected_label}")

    model_prediction = dict(result.get("prediction") or {})
    model_label = model_prediction.get("label")
    model_name = model_prediction.get("name") or model_label
    name = TAXONOMY[corrected_label].get("name", corrected_label)
    agreed = model_label == corrected_label

    category_key = CATEGORY[corrected_label]
    urgency_key = URGENCY[corrected_label]

    out = dict(result)
    out["prediction"] = {
        "label": corrected_label,
        "name": name,
        "kind": "clinician_confirmed",
        "statement": (f"{name} — confirmed on examination by the clinician."
                      if agreed else
                      f"{name} — set by the clinician, overriding the model's "
                      f"reading of {str(model_name).lower()}."),
        "reliable": True,
        # Deliberately absent rather than 1.0: this is not a probability, and
        # the UI must not draw a full confidence bar for a human judgement.
        "confidence": None,
        "margin": None,
        "certainty": "clinician_confirmed",
        "certainty_held_out": None,
        "model_label": model_label,
        "model_name": model_name,
        "model_confidence": model_prediction.get("confidence"),
    }
    out["reliable"] = True
    out["reliability_note"] = (
        "This pattern was set by the clinician from direct examination, not by "
        "the classifier, so the model's measured accuracy does not apply to "
        "it. Everything derived below — the expected hearing and tympanogram, "
        "the disease differential and the cross-checks — follows the "
        "clinician's pattern."
    )
    out["category"] = {
        "key": category_key,
        "name": CATEGORY_LABEL.get(category_key, category_key),
        "probability": None,
        "ranked": [{"key": category_key,
                    "name": CATEGORY_LABEL.get(category_key, category_key),
                    "probability": None}],
    }
    out["urgency"] = {
        "key": urgency_key,
        "name": URGENCY_LABEL.get(urgency_key, urgency_key),
        "probability": None,
        "ranked": [{"key": urgency_key,
                    "name": URGENCY_LABEL.get(urgency_key, urgency_key),
                    "probability": None}],
    }
    out["clinical"] = describe(corrected_label)
    out["evidence"] = _evidence(result.get("measurements") or {}, corrected_label)
    out["ranked"] = [{**r, "corrected": r.get("label") == corrected_label}
                     for r in (result.get("ranked") or [])]
    out["differential"] = out["ranked"][:3]
    # An out-of-distribution image is a statement about the model's training
    # set, and it no longer qualifies a label the model did not produce.
    out["out_of_distribution"] = False
    out["correction"] = {
        "corrected": True,
        "agreed_with_model": agreed,
        "model_label": model_label,
        "model_name": model_name,
        "model_confidence": model_prediction.get("confidence"),
        "model_certainty": model_prediction.get("certainty"),
        "label": corrected_label,
        "name": name,
        "note": note,
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    out["disclaimer"] = (
        "Pattern set by the clinician on direct examination. The model's own "
        "ranking is kept below for the record. A photograph still cannot "
        "exclude disease behind an obscured or partially visible membrane."
    )
    return out


# --------------------------------------------------------------------------
# cross-check against the rest of the battery
# --------------------------------------------------------------------------
def concordance(prediction: dict, analysis: Optional[dict], side: str) -> dict:
    """Does the picture agree with the audiogram and the tympanogram?

    The taxonomy states what each pattern predicts — a perforation should
    give a large ear-canal volume and an air-bone gap; a normal drum should
    give neither. Comparing the pattern's predictions against the measured
    battery produces a specific, checkable disagreement, and a disagreement is
    informative whether or not the classifier is right. An agreement is
    weaker: a predicted pattern is not validated, so agreement corroborates it
    without confirming it.

    WHO IS THE LIKELIER ERROR DEPENDS ON WHERE THE PATTERN CAME FROM, and this
    is the part that changes the advice rather than just the wording. Against a
    PREDICTED pattern — 27% top-1 on unseen photographs — a conflict means the
    image reading is probably wrong, so the action is to look down the scope
    again. Against a pattern a clinician CONFIRMED on examination, that advice
    is backwards: the appearance is the firmer fact, and the conflict points at
    the measurement or at a second pathology the drum does not show. Telling a
    clinician who has just confirmed an intact drum to re-examine it, because a
    30 dB gap does not fit, sends them to check the one thing they are sure of.

    ``analysis`` is a response from ``POST /api/analyze``; None when the
    image was uploaded before any audiometry, in which case there is simply
    nothing to reconcile.
    """
    from app.otoscopy.taxonomy import CONDUCTIVE_CLASSES

    label = prediction["prediction"]["label"]
    confirmed = (prediction.get("prediction") or {}).get("kind") == "clinician_confirmed"
    entry = TAXONOMY.get(label, {})
    agreements: List[dict] = []
    conflicts: List[dict] = []

    if not analysis:
        return {"available": False, "agreements": [], "conflicts": [],
                "note": "No audiometry submitted with this image — nothing to "
                        "cross-check against yet."}

    rules_ear = (analysis.get("rules") or {}).get(side) or {}
    gap = (rules_ear.get("abg") or {}).get("value")
    ear_type = rules_ear.get("type", "")
    tymp = (((analysis.get("immittance") or {}).get(side) or {})
            .get("tympanogram") or {})
    tymp_type = tymp.get("type")

    expects_gap = label in CONDUCTIVE_CLASSES
    lo, hi = entry.get("expected_gap_db", (0, 10))

    name = entry.get("name", label)
    # A predicted pattern is a closest match, not an identification, and every
    # sentence below says so — these lines are quoted on their own elsewhere,
    # where that qualifier is the only thing stopping them reading as a
    # diagnosis. A confirmed pattern needs the opposite treatment: calling a
    # clinician's own examination a "closest reference pattern" would
    # misattribute it to the model.
    if confirmed:
        pattern = f"the confirmed appearance ({name})"
        subject = f"{name}, confirmed on examination,"
        # Agreement with an examined appearance is genuine corroboration from
        # two independent methods, not a hedge about an unvalidated label.
        corroboration = ""
        # Where the examination is the firmer evidence, send the reader to the
        # measurement — not back to the scope.
        reexamine = ("Re-check the measurement: with the appearance confirmed, "
                     "repeat masked bone conduction and the tympanogram with a "
                     "fresh probe seal before reporting. If both stand, look "
                     "for a cause the drum does not show.")
    else:
        pattern = f"the closest reference pattern ({name})"
        subject = f"The closest reference pattern ({name})"
        corroboration = (" This corroborates the pattern match; it does not "
                         "confirm it.")
        reexamine = ("Re-examine the ear first — the pattern match is not "
                     "validated and is the likelier error. If the appearance "
                     "is confirmed, re-check masked bone conduction and repeat "
                     "the tympanogram with a fresh probe seal.")

    if gap is not None:
        if expects_gap and gap >= max(lo, 10):
            agreements.append({
                "title": ("Air-bone gap is consistent with the confirmed appearance"
                          if confirmed else
                          "Air-bone gap is consistent with the closest reference pattern"),
                "detail": (f"{subject} predicts a "
                           f"conductive component and the measured gap is "
                           f"{gap:g} dB." + corroboration),
            })
        elif expects_gap and gap < 10:
            conflicts.append({
                "title": ("The confirmed appearance implies a conductive cause "
                          "but there is no gap" if confirmed else
                          "The image's closest pattern implies a conductive "
                          "cause but there is no gap"),
                "detail": (f"{subject} normally produces "
                           f"a {lo}-{hi} dB air-bone gap, yet the measured gap is "
                           f"only {gap:g} dB."),
                "action": reexamine,
            })
        elif not expects_gap and gap >= 15:
            conflicts.append({
                "title": ("Conductive loss behind a drum confirmed as normal"
                          if confirmed else
                          "Conductive loss while the closest pattern is a "
                          "normal-looking drum"),
                "detail": (f"A {gap:g} dB air-bone gap needs an explanation, and "
                           f"{pattern} does not provide one."),
                # With the drum confirmed normal the gap becomes the finding,
                # and it has a short differential of its own: the pathology is
                # behind an intact membrane. Sending the clinician back to the
                # scope would send them to check the one thing they are sure of.
                "action": ("The drum is confirmed normal, so the cause lies "
                           "behind it: consider ossicular fixation "
                           "(otosclerosis), ossicular discontinuity or a "
                           "third-window disorder such as superior canal "
                           "dehiscence. Confirm with tympanometry and acoustic "
                           "reflexes — absent reflexes behind a Type A trace "
                           "point to otosclerosis."
                           if confirmed else
                           "Re-examine the ear: the pattern match is not "
                           "validated and may have missed a middle-ear cause. "
                           "If the drum is confirmed normal, consider ossicular "
                           "fixation or a third-window disorder; confirm with "
                           "tympanometry and acoustic reflexes."),
            })

    if tymp_type:
        expected = str(entry.get("expected_tympanogram", ""))
        # Compare against the type letters the taxonomy names, as whole
        # tokens. A substring test would find Type "A" inside the word
        # "LARGE" and call a Type A trace consistent with a perforation.
        expected_types = set(re.findall(r"\b([ABC][sd12]?)\b", expected))
        if expected and tymp_type in expected_types:
            agreements.append({
                "title": (f"Tympanogram Type {tymp_type} is consistent with the "
                          "confirmed appearance" if confirmed else
                          f"Tympanogram Type {tymp_type} is consistent with the "
                          "closest reference pattern"),
                "detail": f"{subject} predicts {expected}." + corroboration,
            })
        elif expected:
            conflicts.append({
                "title": ("Tympanogram does not match the confirmed appearance"
                          if confirmed else
                          "Tympanogram does not match the image's closest "
                          "reference pattern"),
                "detail": (f"{subject} predicts "
                           f"{expected}, but the measured trace is Type "
                           f"{tymp_type}."),
                "action": reexamine,
            })

    # An unsafe pattern outranks any reassurance the audiogram might offer.
    # The match itself is unvalidated, so it asks for a direct look rather
    # than asserting the disease; what it must never do is stay silent.
    if label in {"perforation_attic", "tumor"}:
        conflicts.append({
            "title": ("Unsafe appearance confirmed: refer regardless of the "
                      "audiogram" if confirmed else
                      "Unsafe reference pattern: if confirmed on examination, "
                      "refer regardless of the audiogram"),
            "detail": ((f"You have confirmed {name.lower()}. That is managed on "
                        "the examination, not the thresholds: early "
                        "cholesteatoma and small middle-ear masses are "
                        "frequently silent on pure tones, so a reassuring "
                        "audiogram does not change the referral."
                        if confirmed else
                        f"The image most resembles {name.lower()}. That pattern "
                        "is managed on the examination, not the thresholds: "
                        "early cholesteatoma and small middle-ear masses are "
                        "frequently silent on pure tones.")),
            "action": (entry.get("referral", "Urgent ENT referral.")
                       if confirmed else
                       "Examine the ear directly now. If the appearance is "
                       "confirmed: " + entry.get("referral", "Urgent ENT referral.")),
        })

    return {
        "available": True,
        "agreements": agreements,
        "conflicts": conflicts,
        "clinician_confirmed": confirmed,
        "headline": (
            ("The appearance you confirmed and the test battery agree — two "
             "independent methods reaching the same answer."
             if confirmed else
             "The image's closest reference pattern and the test battery agree "
             "(corroboration, not confirmation).")
            if agreements and not conflicts
            else f"{len(conflicts)} finding(s) do not agree — resolve before reporting."
            if conflicts else "Not enough of the battery has been run to cross-check."
        ),
    }
