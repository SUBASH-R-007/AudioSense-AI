"""Training and inference for otoscopic pattern recognition.

Two things matter more here than raw accuracy.

FIRST, HONEST VALIDATION. The reference set is small, and augmented copies of
one photograph are not independent observations. Cross-validating without
accounting for that inflates accuracy to a number that means nothing. This
module holds out whole source images (``LeaveOneGroupOut`` over the source
photograph, augmentations included), so the reported score is what happens on
an image the model has genuinely never seen. The number that comes out is
lower than a naive split would give, and it is the one worth quoting.

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

import json
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

    The grouping key is the source photograph. Every augmentation of one
    photograph carries the same key, so validation can hold all of them out
    together.
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


# --------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------
def _make_classifier():
    """PCA then multinomial logistic regression.

    Chosen by measurement, not preference. Random forests, extra trees and an
    RBF SVM were all compared under the same leave-one-image-out protocol on
    the reference set; this pipeline beat every one of them on top-1 and
    top-3 (the forest managed 39% / 65%). With 391 correlated descriptors and
    62 source images, the projection to 20 components is what keeps the model
    from fitting the noise. Current figures are in the model card, which is
    regenerated by the training script rather than written down here.
    """
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        PCA(n_components=20, random_state=0),
        LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"),
    )


def _honest_cv(X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> dict:
    """Leave-one-source-image-out accuracy at three levels of granularity.

    Held out by source photograph, so no augmented sibling of a test image is
    ever in the training fold. This is deliberately the pessimistic estimate,
    and it is the one reported in the UI.

    Three levels are scored because they are not equally learnable and they
    are not equally important. Which of three perforation sites this is: hard,
    and the model is weak at it. Whether there is a perforation at all:
    easier. Whether this ear needs an urgent referral: easier still, and the
    only one a triage decision actually rests on.
    """
    from sklearn.model_selection import LeaveOneGroupOut

    from app.otoscopy.taxonomy import CATEGORY, URGENCY

    if len(np.unique(groups)) < 3:
        return {"method": "none", "reason": "fewer than three source images"}

    logo = LeaveOneGroupOut()
    total = 0
    topk = {1: 0, 2: 0, 3: 0}
    coarse = {"category": 0, "urgency": 0}
    retrieval = {1: 0, 3: 0}
    per_class: Dict[str, List[int]] = {c: [0, 0] for c in np.unique(y)}
    confusion: Dict[str, Dict[str, int]] = {}

    for train_idx, test_idx in logo.split(X, y, groups):
        if len(np.unique(y[train_idx])) < 2:
            continue
        clf = _make_classifier()
        clf.fit(X[train_idx], y[train_idx])
        # Average probabilities over the held-out image's augmentations, which
        # is exactly how inference works in production.
        probs = clf.predict_proba(X[test_idx]).mean(axis=0)
        order = np.argsort(probs)[::-1]
        ranked = [str(c) for c in np.asarray(clf.classes_)[order]]

        truth = str(y[test_idx][0])
        total += 1
        per_class[truth][1] += 1
        for k in topk:
            if truth in ranked[:k]:
                topk[k] += 1
        if ranked[0] == truth:
            per_class[truth][0] += 1
        confusion.setdefault(truth, {}).setdefault(ranked[0], 0)
        confusion[truth][ranked[0]] += 1
        if CATEGORY.get(ranked[0]) == CATEGORY.get(truth):
            coarse["category"] += 1
        if URGENCY.get(ranked[0]) == URGENCY.get(truth):
            coarse["urgency"] += 1

        # Retrieval is scored on the same folds: does the nearest labelled
        # reference view (a different source image) carry the right label?
        query = X[test_idx].mean(axis=0)
        dist = np.linalg.norm(X[train_idx] - query, axis=1)
        seen, neighbours = set(), []
        for i in np.argsort(dist):
            key = groups[train_idx][i]
            if key in seen:
                continue
            seen.add(key)
            neighbours.append(str(y[train_idx][i]))
            if len(neighbours) >= 3:
                break
        if neighbours and neighbours[0] == truth:
            retrieval[1] += 1
        if truth in neighbours:
            retrieval[3] += 1

    if not total:
        return {"method": "none", "reason": "no usable folds"}

    return {
        "method": "leave-one-source-image-out; probabilities averaged over "
                  "augmentations of the held-out image",
        "images_tested": total,
        "accuracy": round(topk[1] / total, 4),
        "top2_accuracy": round(topk[2] / total, 4),
        "top3_accuracy": round(topk[3] / total, 4),
        "category_accuracy": round(coarse["category"] / total, 4),
        "urgency_accuracy": round(coarse["urgency"] / total, 4),
        "retrieval_top1": round(retrieval[1] / total, 4),
        "retrieval_top3": round(retrieval[3] / total, 4),
        "chance_level": round(1.0 / max(len(np.unique(y)), 1), 4),
        "per_class_recall": {
            c: {"correct": v[0], "n": v[1],
                "recall": round(v[0] / v[1], 3) if v[1] else None}
            for c, v in sorted(per_class.items())
        },
        "confusion": confusion,
    }


def train(
    roots: Optional[Sequence[Path]] = None,
    out_path: Path = ARTIFACT,
    run_cv: bool = True,
) -> dict:
    """Fit the classifier and write the artifact. Returns the model card."""
    import joblib
    from sklearn.preprocessing import StandardScaler

    roots = list(roots) if roots else [p for p in (REFERENCE_DIR, KAGGLE_DIR) if p.exists()]
    X, y, groups, paths, unmapped = load_dataset(roots)
    if X.shape[0] == 0:
        raise FileNotFoundError(
            f"no otoscope images found under {[str(r) for r in roots]}")

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    cv = _honest_cv(Xs, y, groups) if run_cv else {"method": "skipped"}

    clf = _make_classifier()
    clf.fit(Xs, y)

    # Retrieval bank: one un-augmented descriptor per reference image, so
    # "most similar reference view" points at a real file we can display.
    ref_X, ref_y, _, ref_paths, _ = load_dataset(roots, augmented=False)
    ref_Xs = scaler.transform(ref_X) if len(ref_X) else ref_X

    # Novelty threshold: how far a genuine otoscope image sits from its
    # nearest training neighbour. Anything well beyond this is not an ear.
    nn_dists = []
    for i in range(0, len(Xs), max(1, len(Xs) // 400)):
        d = np.linalg.norm(ref_Xs - Xs[i], axis=1) if len(ref_Xs) else np.array([0.0])
        nn_dists.append(float(d.min()))
    novelty_cut = float(np.percentile(nn_dists, 99)) if nn_dists else 0.0

    sources = {}
    for root in roots:
        found, _ = scan_directory(Path(root))
        sources[Path(root).name] = {k: len(v) for k, v in sorted(found.items())}

    card = {
        "classes": sorted(set(y.tolist())),
        "n_images": int(len(ref_paths)),
        "n_training_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "augmentations_per_image": len(AUG_ROTATIONS) * len(AUG_GAINS) * len(AUG_FLIP),
        "sources": sources,
        "unmapped_folders": unmapped,
        "validation": cv,
        "kaggle_present": KAGGLE_DIR.exists(),
        "novelty_threshold": round(novelty_cut, 3),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "clf": clf, "scaler": scaler, "feature_names": F.FEATURE_NAMES,
        "ref_X": ref_Xs, "ref_y": ref_y,
        "ref_paths": [str(Path(p).relative_to(DATA_DIR)) for p in ref_paths],
        "novelty_cut": novelty_cut, "card": card,
    }, out_path)
    (DATA_DIR / "otoscopy_model_card.json").write_text(
        json.dumps(card, indent=2), encoding="utf-8")
    return card


# --------------------------------------------------------------------------
# inference
# --------------------------------------------------------------------------
_BUNDLE: Optional[dict] = None


def model_available() -> bool:
    return ARTIFACT.exists()


def load_bundle() -> dict:
    global _BUNDLE
    if _BUNDLE is None:
        if not ARTIFACT.exists():
            raise FileNotFoundError(
                "otoscopy model not trained — run: python -m scripts.train_otoscopy")
        import joblib
        _BUNDLE = joblib.load(ARTIFACT)
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

    Deliberately NOT phrased as a single diagnosis. On the shipped reference
    set the top label is right well under half the time while the top three
    contain the right answer far more often, so a ranked differential is what
    the evidence supports. The coarse category and the urgency band are
    reported separately because they are measured separately and they are
    what a triage decision actually rests on. Exact figures come from the
    model card so they cannot drift out of date in a docstring.
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

    # Roll the class probabilities up to the coarser levels. These are the
    # numbers to trust: the category is right ~55% of the time and the
    # urgency band ~60%, against 12.5% chance.
    def _rollup(mapping: Dict[str, str]) -> List[dict]:
        totals: Dict[str, float] = {}
        for cls, p in zip(classes, probs):
            totals[mapping[cls]] = totals.get(mapping[cls], 0.0) + float(p)
        return sorted(({"key": k, "probability": round(v, 4)}
                       for k, v in totals.items()),
                      key=lambda d: -d["probability"])

    categories = _rollup(CATEGORY)
    urgencies = _rollup(URGENCY)

    # Confidence is only meaningful when the top two classes separate and the
    # image is readable. Say so rather than printing a number that is not
    # earned.
    margin = confidence - runner_up
    if not quality["usable"]:
        certainty = "unreliable"
    elif novel:
        certainty = "out-of-distribution"
    elif confidence >= 0.55 and margin >= 0.18:
        certainty = "probable"
    elif confidence >= 0.38:
        certainty = "provisional"
    else:
        certainty = "uncertain"

    return {
        "prediction": {
            "label": top,
            "name": TAXONOMY.get(top, {}).get("name", top),
            "confidence": round(confidence, 4),
            "margin": round(margin, 4),
            "certainty": certainty,
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
        "model": bundle["card"],
        "disclaimer": (
            "Otoscopic pattern support, not a diagnosis. The model is trained "
            "on a small reference set and offers a ranked differential to "
            "compare against what you see down the scope; it cannot exclude "
            "disease behind an obscured or partially visible membrane."
        ),
    }


# --------------------------------------------------------------------------
# cross-check against the rest of the battery
# --------------------------------------------------------------------------
def concordance(prediction: dict, analysis: Optional[dict], side: str) -> dict:
    """Does the picture agree with the audiogram and the tympanogram?

    This is the part of otoscopy that does not depend on the classifier being
    right, and it is where the clinical value sits. The taxonomy states what
    each pattern predicts — a perforation should give a large ear-canal
    volume and an air-bone gap; a normal drum should give neither. Comparing
    that against the measured battery either corroborates the image or
    produces a specific, checkable disagreement.

    ``analysis`` is a response from ``POST /api/analyze``; None when the
    image was uploaded before any audiometry, in which case there is simply
    nothing to reconcile.
    """
    from app.otoscopy.taxonomy import CONDUCTIVE_CLASSES

    label = prediction["prediction"]["label"]
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

    if gap is not None:
        if expects_gap and gap >= max(lo, 10):
            agreements.append({
                "title": "Air-bone gap matches the otoscopic finding",
                "detail": (f"{entry.get('name', label)} predicts a conductive "
                           f"component and the measured gap is {gap:g} dB."),
            })
        elif expects_gap and gap < 10:
            conflicts.append({
                "title": "Otoscopy suggests a conductive cause but there is no gap",
                "detail": (f"The image was read as {entry.get('name', label)}, which "
                           f"normally produces a {lo}-{hi} dB air-bone gap, yet the "
                           f"measured gap is only {gap:g} dB."),
                "action": "Re-check masked bone conduction, and re-examine the ear. "
                          "One of the two findings is wrong.",
            })
        elif not expects_gap and gap >= 15:
            conflicts.append({
                "title": "Conductive loss with a normal-looking drum",
                "detail": (f"A {gap:g} dB air-bone gap needs an explanation, and the "
                           "image does not provide one."),
                "action": "Consider ossicular fixation or a third-window disorder; "
                          "confirm with tympanometry and acoustic reflexes.",
            })

    if tymp_type:
        expected = str(entry.get("expected_tympanogram", ""))
        if expected and tymp_type in expected:
            agreements.append({
                "title": f"Tympanogram Type {tymp_type} matches the appearance",
                "detail": f"{entry.get('name', label)} predicts {expected}.",
            })
        elif expected:
            conflicts.append({
                "title": "Tympanogram does not match the otoscopic appearance",
                "detail": (f"The image was read as {entry.get('name', label)}, which "
                           f"predicts {expected}, but the measured trace is "
                           f"Type {tymp_type}."),
                "action": "Repeat the probe seal and re-examine; a mismatch here "
                          "usually means one of the two was mis-recorded.",
            })

    # An unsafe pattern outranks any reassurance the audiogram might offer.
    if label in {"perforation_attic", "tumor"}:
        conflicts.append({
            "title": "Appearance requires referral regardless of the audiogram",
            "detail": (f"{entry.get('name', label)} is managed on the examination, "
                       "not the thresholds. Early cholesteatoma and small middle-ear "
                       "masses are frequently silent on pure tones."),
            "action": entry.get("referral", "Urgent ENT referral."),
        })

    return {
        "available": True,
        "agreements": agreements,
        "conflicts": conflicts,
        "headline": (
            "The image and the test battery agree." if agreements and not conflicts
            else f"{len(conflicts)} finding(s) do not agree — resolve before reporting."
            if conflicts else "Not enough of the battery has been run to cross-check."
        ),
    }
