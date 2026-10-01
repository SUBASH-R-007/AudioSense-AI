"""Clinical safety layer — red-flag referrals and test-validity checks.

Two jobs that matter more than any classification:

1. RED FLAGS. Some audiograms are not a fitting problem but a medical
   emergency or a tumour screen. Sudden sensorineural hearing loss is
   treatable with corticosteroids but the window is days; asymmetric
   sensorineural loss can be the first sign of a vestibular schwannoma.
   Missing either is the costliest mistake this tool could make.

2. VALIDITY. An unmasked audiogram can record the *other* ear (a "shadow
   curve") and look like real hearing that isn't there. Flagging when
   masking was indicated stops the rest of the pipeline from confidently
   interpreting an invalid test.

Thresholds below follow criteria in common clinical use; exact cut-offs
vary between guidelines, so every flag states its own rule and the payload
is advisory — it recommends referral, it does not diagnose.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.schemas import (
    AC_FREQS, BC_FREQS, PTA_FREQS, ThresholdValue, ear_to_numeric,
)

#: Interaural attenuation for supra-aural earphones, dB. Sound presented
#: above this level can cross the skull and be heard by the opposite
#: cochlea, so the non-test ear must be masked.
INTERAURAL_ATTENUATION_AC = 40
#: Bone conduction crosses the skull essentially unattenuated.
INTERAURAL_ATTENUATION_BC = 0

#: Sudden SNHL: ≥30 dB over ≥3 contiguous frequencies developing within 72 h.
SUDDEN_DROP_DB = 30
SUDDEN_CONTIGUOUS_FREQS = 3

#: A single threshold at or better than this is within normal limits. The BSA
#: Recommended Procedure for pure-tone audiometry (2018) starts its first
#: impairment descriptor, "mild", at 21 dB HL; rules.hearing_type uses the
#: same edge for bone conduction (BC_NORMAL_MAX_DB). This is a per-frequency
#: limit. The WHO (2021) grade in rules.who_grade is a different measure — a
#: four-frequency average, in which exactly 20 dB HL is already "mild" — so
#: an ear at 20 dB HL everywhere grades mild there while every one of its
#: thresholds is within normal limits here.
NORMAL_LIMIT_DB = 20
#: An air-bone gap above this is a conductive component (ASHA convention;
#: the same "> 10 dB" rule rules.hearing_type applies).
SIGNIFICANT_ABG_DB = 10

#: Interaural asymmetry criteria for a retrocochlear referral:
#:  - ≥20 dB at any single frequency from 0.5 to 4 kHz — the UK Department
#:    of Health protocol (Neary et al. 1996);
#:  - ≥15 dB at two or more frequencies — Cueva (2004). The BAA Onward
#:    Referral Guidance (2023) and NICE NG98 (2018, rec. 1.3.2) ask for the
#:    two to be adjacent among 0.5/1/2/4/8 kHz; counting any two tested
#:    frequencies is the more sensitive superset.
#: The BAA applies its rule to "air or bone conduction test frequencies", so
#: the comparison is made in bone conduction as well as in air: a cochlear
#: asymmetry is found even in the ear that is better by air conduction.
#: Every counted frequency must also be outside normal limits in the poorer
#: ear (NORMAL_LIMIT_DB) — the guidance is for asymmetric hearing LOSS.
#: A single-frequency difference at 250 or 8000 Hz alone meets none of these
#: protocols, and 8 kHz cannot be checked against bone conduction at all.
ASYM_SINGLE_DB = 20
ASYM_SINGLE_FREQS = (500, 1000, 2000, 4000)
ASYM_PAIR_DB = 15
ASYM_PAIR_COUNT = 2


def _n(ear) -> Dict[int, Optional[float]]:
    return ear_to_numeric(ear or {})


# ---------------------------------------------------------------- asymmetry


def _asymmetry_rule(diffs: Dict[int, float]) -> dict:
    """Apply the single-frequency and two-frequency criteria to ``diffs``."""
    single = [f for f in AC_FREQS
              if f in ASYM_SINGLE_FREQS and diffs.get(f, 0) >= ASYM_SINGLE_DB]
    pair = [f for f in AC_FREQS if diffs.get(f, 0) >= ASYM_PAIR_DB]
    return {"met": bool(single) or len(pair) >= ASYM_PAIR_COUNT,
            "single": single, "pair": pair}


def _asymmetry_reasons(rule: dict, measure: str = "") -> List[str]:
    """The criteria ``rule`` met, worded for the referral.

    ``measure`` names the conduction the difference was read in (for example
    " in bone conduction") when the air-conduction audiogram alone would not
    show it to the reader.
    """
    reasons = []
    if rule["single"]:
        reasons.append(f"≥{ASYM_SINGLE_DB} dB interaural difference{measure} at "
                       f"{rule['single']} Hz")
    if len(rule["pair"]) >= ASYM_PAIR_COUNT:
        reasons.append(f"≥{ASYM_PAIR_DB} dB interaural difference{measure} at "
                       f"{rule['pair']} Hz")
    return reasons


def _cochlear_threshold(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """The cochlear threshold at one frequency, as the audiogram bounds it.

    Bone conduction measures the cochlea, and in a real ear it cannot be
    poorer than air conduction, so the better of the two is taken. Without
    bone conduction, air conduction is an upper bound on the cochlear
    threshold — which is how an ear not tested by bone is read in practice.
    """
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


def _poorer_ear_asymmetry(ac_p, ac_q, bc_p, bc_q) -> dict:
    """Asymmetry with ``p`` as the poorer ear, in air and in the cochlea.

    Air conduction answers "is one ear worse?"; only the sensorineural part
    of that difference is a vestibular-schwannoma question. Two comparisons:

    1. Where ``p`` is the poorer ear by air conduction, per frequency:

       - no significant air-bone gap in ``p``: its air threshold is its
         cochlear threshold, so the air difference counts as sensorineural;
       - a gap with ``p``'s cochlea within normal limits: the whole
         difference sits in the middle ear (conductive);
       - a gap with ``p``'s cochlea impaired (mixed loss): the bone-
         conduction difference is the sensorineural asymmetry;
       - bone conduction not measured (always so at 8 kHz): the frequency
         takes the type bone conduction showed at an adjacent asymmetric
         frequency, the way 8 kHz is read from 4 kHz; with no such
         neighbour, or a sensorineural one, it is assumed sensorineural.

    2. Wherever ``p``'s bone conduction was measured: ``p``'s cochlea against
       ``q``'s, whether or not ``p`` is also the poorer ear by air. A
       conductive loss in ``q`` can make ``q`` the poorer ear by air while
       ``p`` has the worse cochlea; the BAA Onward Referral Guidance (2023)
       applies its asymmetry rule to "air or bone conduction test
       frequencies", so that cochlear asymmetry is a retrocochlear question
       in ``p`` all the same.

    ``q``'s cochlear threshold is its bone conduction where measured,
    otherwise its air threshold (an upper bound, so the cochlear difference
    found is never larger than the real one).
    """
    ac_diffs: Dict[int, float] = {}
    for f in AC_FREQS:
        a_p, a_q = ac_p.get(f), ac_q.get(f)
        # Two ears that are both within normal limits are not an asymmetric
        # hearing loss, however far apart: a referral needs a loss.
        if a_p is not None and a_q is not None and a_p > NORMAL_LIMIT_DB \
                and a_p - a_q > 0:
            ac_diffs[f] = a_p - a_q
    air = _asymmetry_rule(ac_diffs)

    # Cochlear differences shown by a measured bone-conduction threshold in p.
    measured: Dict[int, float] = {}
    assumed: Dict[int, float] = {}
    untested: Dict[int, float] = {}
    conductive: List[int] = []
    for f, d in ac_diffs.items():
        if d < ASYM_PAIR_DB:
            continue  # below both criteria; cannot contribute either way
        a_p, a_q = ac_p[f], ac_q[f]
        b_p, b_q = bc_p.get(f), bc_q.get(f)
        c_q = _cochlear_threshold(a_q, b_q)
        if b_p is None:
            untested[f] = a_p - c_q
        elif a_p - b_p <= SIGNIFICANT_ABG_DB:
            measured[f] = a_p - c_q
        elif b_p <= NORMAL_LIMIT_DB:
            conductive.append(f)
        elif b_q is None and a_q > NORMAL_LIMIT_DB:
            # The better ear's own air-bone gap is unknown, so the cochlear
            # difference cannot be separated from the air difference.
            assumed[f] = d
        elif b_p - c_q >= ASYM_PAIR_DB:
            measured[f] = b_p - c_q
        else:
            conductive.append(f)

    # 2. The cochlear comparison in its own right, in either direction of the
    # air-conduction difference. The poorer cochlea must itself be outside
    # normal limits, as the poorer ear must be in air.
    bone_only: List[int] = []
    for f in AC_FREQS:
        b_p = bc_p.get(f)
        c_q = _cochlear_threshold(ac_q.get(f), bc_q.get(f))
        if b_p is None or c_q is None:
            continue
        c_p = _cochlear_threshold(ac_p.get(f), b_p)
        if c_p > NORMAL_LIMIT_DB and c_p - c_q > measured.get(f, 0):
            measured[f] = c_p - c_q
            if f not in ac_diffs:
                bone_only.append(f)

    sn_freqs = {f for f, v in measured.items() if v >= ASYM_PAIR_DB}
    read_as_conductive: List[int] = []
    for f, value in untested.items():
        i = AC_FREQS.index(f)
        neighbours = AC_FREQS[max(0, i - 1):i] + AC_FREQS[i + 1:i + 2]
        if any(n in conductive for n in neighbours) and \
                not any(n in sn_freqs for n in neighbours):
            read_as_conductive.append(f)
        else:
            assumed[f] = value

    # Per frequency, the larger of the measured and the assumed cochlear
    # difference counts, and remembers which it was.
    counted: Dict[int, float] = {}
    source: Dict[int, str] = {}
    for f, v in assumed.items():
        counted[f], source[f] = v, "assumed"
    for f, v in measured.items():
        if v >= counted.get(f, v):
            counted[f], source[f] = v, "measured"
    return {
        "air": air,
        "cochlea": _asymmetry_rule(counted),
        # The criterion is met by measured bone conduction alone — the type
        # of the asymmetry is shown, not assumed.
        "confirmed": _asymmetry_rule(measured)["met"],
        "ac_diffs": ac_diffs,
        "sn_diffs": counted,
        "assumed_freqs": sorted(f for f, s in source.items() if s == "assumed"),
        "measured_sn_freqs": sorted(sn_freqs),
        "bone_only_freqs": sorted(bone_only),
        "conductive_freqs": sorted(conductive),
        "untested_read_as_conductive": sorted(read_as_conductive),
    }


def asymmetry_check(right_ac, left_ac, right_bc=None, left_bc=None) -> dict:
    """Interaural difference screen for retrocochlear referral.

    ``flag`` means a retrocochlear screen (MRI with contrast, to exclude a
    vestibular schwannoma) is indicated: the poorer ear has a hearing loss
    outside normal limits at the asymmetric frequencies AND the asymmetry is
    sensorineural (in bone conduction, or with no air-bone gap) or its type
    is unknown. Vestibular-schwannoma screening criteria are defined for
    asymmetric sensorineural loss — the BAA guidance (2023) and NICE NG98
    (rec. 1.3.2) route MRI for asymmetric sensorineural hearing loss and
    conductive loss to ENT — so an asymmetry carried entirely by an air-bone
    gap is returned as ``kind == "conductive"`` with ``flag`` False.

    ``poorer_ear`` is the ear with the flagged asymmetry: for a sensorineural
    asymmetry, the ear with the worse cochlea, which need not be the ear that
    is worse by air conduction.
    """
    r, l = _n(right_ac), _n(left_ac)
    rb, lb = _n(right_bc), _n(left_bc)
    diffs: Dict[int, float] = {}
    for f in AC_FREQS:
        if r.get(f) is not None and l.get(f) is not None:
            diffs[f] = round(abs(r[f] - l[f]), 1)
    criterion = (
        f"Poorer ear outside normal limits (> {NORMAL_LIMIT_DB} dB HL) with "
        f"≥{ASYM_SINGLE_DB} dB at one frequency 0.5–4 kHz (DoH, Neary 1996) or "
        f"≥{ASYM_PAIR_DB} dB at two or more frequencies (Cueva 2004), in air or "
        "bone conduction (BAA 2023); a retrocochlear screen when the asymmetry "
        "is sensorineural"
    )
    empty = {"flag": False, "kind": None, "conductive": False, "diffs": diffs,
             "max_diff": max(diffs.values()) if diffs else None,
             "poorer_ear": None, "reasons": [], "assumed_sensorineural_freqs": [],
             "type_confirmed": False, "conductive_freqs": [],
             "untested_read_as_conductive": [], "bone_only_freqs": [],
             "bone_conduction_only": False,
             "other_ear_conductive": None, "other_ear_bc_not_measured": [],
             "criterion": criterion, "normal_limit_db": NORMAL_LIMIT_DB}
    if not diffs:
        return {**empty, "reason": "insufficient paired data"}

    sides = {"right": _poorer_ear_asymmetry(r, l, rb, lb),
             "left": _poorer_ear_asymmetry(l, r, lb, rb)}

    def weight(side: str, key: str) -> float:
        rule = sides[side][key]
        diffs_used = sides[side]["sn_diffs" if key == "cochlea" else "ac_diffs"]
        return sum(diffs_used[f] for f in set(rule["single"]) | set(rule["pair"]))

    sn = [s for s in ("right", "left") if sides[s]["cochlea"]["met"]]
    air = [s for s in ("right", "left") if sides[s]["air"]["met"]]
    if sn:
        poorer = max(sn, key=lambda s: weight(s, "cochlea"))
        kind, rule = "sensorineural", sides[poorer]["cochlea"]
    elif air:
        poorer = max(air, key=lambda s: weight(s, "air"))
        kind, rule = "conductive", sides[poorer]["air"]
    else:
        return empty

    other = "left" if poorer == "right" else "right"
    ear, opp = sides[poorer], sides[other]
    counted = set(rule["single"]) | set(rule["pair"])

    measure = ""
    bone_only: List[int] = []
    other_conductive = None
    bc_not_measured: List[int] = []
    if kind == "sensorineural":
        bone_only = sorted(counted & set(ear["bone_only_freqs"]))
        if bone_only and set(bone_only) == counted:
            # Nothing on the air-conduction audiogram shows this ear as the
            # poorer one; the reason must say where the difference is.
            measure = " in bone conduction"
        if opp["air"]["met"] and opp["conductive_freqs"]:
            # The other ear is the poorer by air, conductively: a middle-ear
            # finding of its own, beside the cochlear asymmetry here.
            other_conductive = {"ear": other, "freqs": opp["conductive_freqs"]}
    else:
        # The other ear without bone conduction can hide a cochlear
        # asymmetry: its air thresholds bound its cochlea only from above.
        own, theirs = (r, l) if poorer == "right" else (l, r)
        own_bc, their_bc = (rb, lb) if poorer == "right" else (lb, rb)
        potential: Dict[int, float] = {}
        for f in BC_FREQS:
            a_o = theirs.get(f)
            c_p = _cochlear_threshold(own.get(f), own_bc.get(f))
            if a_o is None or c_p is None or their_bc.get(f) is not None:
                continue
            if a_o > NORMAL_LIMIT_DB and a_o - c_p > 0:
                potential[f] = a_o - c_p
        hidden = _asymmetry_rule(potential)
        if hidden["met"]:
            bc_not_measured = sorted(set(hidden["single"]) | set(hidden["pair"]))

    return {
        **empty,
        "flag": kind == "sensorineural",
        "kind": kind,
        "conductive": kind == "conductive",
        "poorer_ear": poorer,
        "reasons": _asymmetry_reasons(rule, measure),
        # Frequencies counted as sensorineural only because bone conduction
        # was not measured there — the referral says so.
        "assumed_sensorineural_freqs": (
            [f for f in ear["assumed_freqs"] if f in counted]
            if kind == "sensorineural" else []),
        # True when measured bone conduction meets the criterion on its own,
        # so the asymmetry is shown to be sensorineural, not assumed to be.
        "type_confirmed": kind == "sensorineural" and ear["confirmed"],
        # Counted frequencies at which this ear is not the poorer by air: the
        # difference is visible only in bone conduction.
        "bone_only_freqs": bone_only,
        "bone_conduction_only": bool(measure),
        "other_ear_conductive": other_conductive,
        # Conductive asymmetry only: frequencies at which the other ear, not
        # tested by bone conduction, could carry a cochlear asymmetry.
        "other_ear_bc_not_measured": bc_not_measured,
        "conductive_freqs": ear["conductive_freqs"] if kind == "conductive" else [],
        "untested_read_as_conductive": (
            ear["untested_read_as_conductive"] if kind == "conductive" else []),
    }


# ------------------------------------------------------------- sudden SNHL


def _contiguous_run(freqs) -> List[int]:
    """Longest run of adjacent audiometric frequencies contained in ``freqs``.

    "Consecutive frequencies" are adjacent test frequencies; this audiogram
    is tested in octaves (250–8000 Hz), so adjacent means adjacent octaves.
    """
    best: List[int] = []
    run: List[int] = []
    for f in AC_FREQS:
        if f in freqs:
            run.append(f)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    return best


def _sensorineural_threshold(ac_db: Optional[float],
                             bc_db: Optional[float]) -> Optional[float]:
    """The sensorineural part of one threshold.

    Air conduction where there is no significant air-bone gap (an unmeasured
    gap counts as none, so an ear without bone conduction is read as
    sensorineural — the conservative reading for an emergency screen);
    where there is a gap, the bone-conduction threshold, which is the
    cochlear component of a mixed loss.
    """
    if ac_db is None:
        return None
    if bc_db is None or ac_db - bc_db <= SIGNIFICANT_ABG_DB:
        return ac_db
    return bc_db


def sudden_loss_check(
    ac: Dict[int, Optional[ThresholdValue]],
    bc: Dict[int, Optional[ThresholdValue]],
    onset: str = "unknown",
    baseline_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
    opposite_ac: Optional[Dict[int, Optional[ThresholdValue]]] = None,
    opposite_bc: Optional[Dict[int, Optional[ThresholdValue]]] = None,
) -> dict:
    """Screen for sudden sensorineural hearing loss (an ENT emergency).

    AAO-HNSF Clinical Practice Guideline: Sudden Hearing Loss (Stachler et
    al. 2012; update Chandrasekhar et al. 2019): ≥30 dB sensorineural loss
    at three consecutive audiometric frequencies developing within 72 hours.
    Because premorbid audiometry is generally unavailable, the guideline
    defines the loss relative to the opposite ear's thresholds.

    With a documented earlier audiogram the drop is measured directly.
    Without one, the loss is measured against the opposite ear, and a PTA of
    30 dB HL or more in the sensorineural thresholds also qualifies (it
    catches a bilateral sudden loss, where the opposite ear is no reference).
    Where the opposite ear was not tested at a frequency, the loss there is
    counted from 0 dB HL — the same assumption of previously normal hearing
    the PTA rule makes — and the result says so. None of these confirms the
    72-hour onset, so the check relies on reported onset and returns a
    *conditional* flag that says exactly what would make it an emergency.

    "Sensorineural loss" is read from the sensorineural thresholds
    (``_sensorineural_threshold``): a sudden cochlear loss on top of a
    conductive one — common where chronic otitis media is — is a mixed
    audiogram whose bone conduction carries the sudden loss, and it is SSNHL
    all the same.
    """
    current = _n(ac)

    if baseline_ac:
        base = _n(baseline_ac)
        best = _contiguous_run([
            f for f in AC_FREQS
            if base.get(f) is not None and current.get(f) is not None
            and current[f] - base[f] >= SUDDEN_DROP_DB
        ])
        if len(best) >= SUDDEN_CONTIGUOUS_FREQS:
            return {
                "flag": True,
                "urgency": "emergency",
                "confirmed": True,
                "freqs": best,
                "basis": "baseline",
                "message": (
                    f"≥{SUDDEN_DROP_DB} dB drop across {len(best)} contiguous "
                    "frequencies versus the previous audiogram — consistent with "
                    "sudden sensorineural hearing loss."
                ),
                "action": "Immediate ENT referral. Corticosteroid treatment is "
                          "time-critical; benefit falls sharply after ~2 weeks.",
            }

    # No baseline: use reported onset plus a substantial sensorineural loss.
    bc_n = _n(bc)
    sn = {f: _sensorineural_threshold(current.get(f), bc_n.get(f))
          for f in AC_FREQS}
    pta_vals = [current[f] for f in PTA_FREQS if current.get(f) is not None]
    pta = sum(pta_vals) / len(pta_vals) if pta_vals else None
    gaps = [current[f] - bc_n[f] for f in PTA_FREQS
            if current.get(f) is not None and bc_n.get(f) is not None]
    sensorineural = (sum(gaps) / len(gaps) <= 10) if gaps else True
    sn_vals = [sn[f] for f in PTA_FREQS if sn[f] is not None]
    sn_pta = sum(sn_vals) / len(sn_vals) if sn_vals else None

    pure_sn = pta is not None and pta >= SUDDEN_DROP_DB and sensorineural
    # The cochlear component of a mixed loss: the sensorineural thresholds
    # average ≥30 dB HL beneath an air-bone gap.
    mixed = (not pure_sn and sn_pta is not None and sn_pta >= SUDDEN_DROP_DB)
    substantial = pure_sn or mixed
    # Frequencies whose sensorineural threshold is bone conduction.
    bc_used = [f for f in AC_FREQS
               if sn[f] is not None and current.get(f) is not None
               and sn[f] != current[f]]

    # The guideline's own reference when no earlier audiogram exists: ≥30 dB
    # sensorineural loss relative to the opposite ear at three consecutive
    # frequencies. A low- or high-frequency sudden loss can meet this with a
    # four-frequency PTA well under 30 dB HL. The opposite ear is read the
    # same way as this one — its sensorineural threshold — so like is compared
    # with like, and a conductive loss in the opposite ear does not hide a
    # sudden cochlear loss here.
    versus: List[int] = []
    unreferenced: List[int] = []
    if not baseline_ac:
        opp_ac, opp_bc = _n(opposite_ac), _n(opposite_bc)
        drop: List[int] = []
        no_ref: List[int] = []
        for f in AC_FREQS:
            if sn[f] is None:
                continue
            ref = (_sensorineural_threshold(opp_ac.get(f), opp_bc.get(f))
                   if opp_ac.get(f) is not None else opp_bc.get(f))
            if ref is None:
                # Opposite ear not tested here: counted from audiometric zero.
                ref = 0.0
                no_ref.append(f)
            if sn[f] - ref >= SUDDEN_DROP_DB:
                drop.append(f)
        versus = _contiguous_run(drop)
        if len(versus) < SUDDEN_CONTIGUOUS_FREQS:
            versus = []
        unreferenced = [f for f in versus if f in no_ref]

    if versus and not unreferenced:
        basis = "opposite_ear"
    elif substantial:
        basis = "pta"
    elif versus:
        basis = "audiometric_zero"
    else:
        return {"flag": False, "urgency": "none", "confirmed": False, "freqs": [],
                "message": None, "action": None}

    freqs = versus if basis != "pta" else []
    # Name the frequencies read from bone conduction wherever the finding
    # rests on them (not for a PTA quoted in air conduction).
    bc_note = ([f for f in (freqs or PTA_FREQS) if f in bc_used]
               if basis != "pta" or mixed else [])
    if basis == "opposite_ear":
        finding = (f"this ear's sensorineural thresholds are ≥{SUDDEN_DROP_DB} dB "
                   f"worse than the opposite ear at {versus} Hz — ≥{SUDDEN_DROP_DB} "
                   f"dB sensorineural loss at {SUDDEN_CONTIGUOUS_FREQS} consecutive "
                   "frequencies, measured against the opposite ear as the AAO-HNSF "
                   "guideline does when no earlier audiogram exists.")
    elif basis == "pta":
        finding = (f"this ear has a sensorineural loss of "
                   f"{(pta if pure_sn else sn_pta):.0f} dB HL (PTA"
                   + (" of the bone-conduction component" if mixed else "") + ").")
    else:
        finding = (f"this ear's sensorineural thresholds are ≥{SUDDEN_DROP_DB} dB HL "
                   f"at {versus} Hz. The opposite ear was not tested at "
                   f"{unreferenced} Hz, so the loss there is counted from 0 dB HL, "
                   "which assumes this ear heard normally before.")
    if bc_note:
        finding += (f" At {bc_note} Hz the sensorineural threshold is bone "
                    "conduction beneath an air-bone gap: a cochlear loss on top of "
                    "a conductive one.")
    confirm = (" Test the opposite ear, and obtain any earlier audiogram, to "
               "confirm the reference." if basis == "audiometric_zero" else "")

    if onset == "sudden":
        return {
            "flag": True,
            "urgency": "emergency",
            "confirmed": False,
            "freqs": freqs,
            "basis": basis,
            "unreferenced_freqs": unreferenced,
            "message": (f"Reported sudden onset, and {finding} Treat as sudden "
                        "SNHL until proven otherwise."),
            "action": ("Immediate ENT referral. Corticosteroid treatment is "
                       "time-critical; benefit falls sharply after ~2 weeks."
                       + confirm),
        }
    if onset == "unknown":
        return {
            "flag": False,
            "urgency": "ask",
            "confirmed": False,
            "freqs": freqs,
            "basis": basis,
            "unreferenced_freqs": unreferenced,
            "message": (f"Onset not recorded. {finding[0].upper()}{finding[1:]} If "
                        "this loss appeared within 72 hours, it meets the "
                        "sudden-SNHL definition and is an emergency."),
            "action": ("Ask the patient when the loss began before scheduling "
                       "routine follow-up." + confirm),
        }
    return {"flag": False, "urgency": "none", "confirmed": False, "freqs": [],
            "message": None, "action": None}


# ---------------------------------------------------------------- masking


def masking_check(test_ac, test_bc, other_ac, other_bc, masked: bool = False,
                  transducer: str = None) -> dict:
    """Was masking required to make these thresholds trustworthy?

    Delegates to ``masking.masking_plan``, which holds the full per-frequency
    rule set, the transducer-dependent interaural attenuation and the masking
    dilemma. This module used to carry a second, narrower copy of the rules —
    one air-conduction condition instead of two, and a 10 dB bone-conduction
    trigger instead of 15 — so the safety layer and a clinician working from
    the reference could disagree about the same ear.
    """
    from app.clinical.masking import DEFAULT_TRANSDUCER, masking_plan

    return masking_plan(test_ac, test_bc, other_ac, other_bc,
                        transducer or DEFAULT_TRANSDUCER, masked)


# ------------------------------------------------------------------ bundle


#: Display priority — an emergency must never be pushed below anything else.
ALERT_ORDER = {"emergency": 0, "urgent": 1, "validity": 2, "info": 3}


def sort_alerts(alerts: List[dict]) -> List[dict]:
    """Sort alerts by clinical urgency, in place."""
    alerts.sort(key=lambda a: ALERT_ORDER.get(a["level"], 9))
    return alerts


def _asymmetry_alert(asym: dict, masking: dict) -> dict:
    """The referral an asymmetry warrants, routed by its type.

    Imaging for a vestibular schwannoma answers an asymmetric sensorineural
    loss; an asymmetry carried by an air-bone gap is middle-ear disease and
    goes to ENT / otology (BAA Onward Referral Guidance, 2023). Both are
    "urgent" — a one-sided conductive loss can be a cholesteatoma.
    """
    side = asym["poorer_ear"]
    other = "left" if side == "right" else "right"
    reasons = "; ".join(asym["reasons"])

    if asym["kind"] == "sensorineural":
        assumed = asym["assumed_sensorineural_freqs"]
        detail = f"{reasons}, with the {side} ear outside normal limits."
        bone_only = asym.get("bone_only_freqs") or []
        if bone_only:
            # Bone conduction crosses the skull unattenuated, so a measured
            # bone-conduction asymmetry cannot be the better cochlea's shadow;
            # an air-bone gap in the other ear is what hides it in air.
            where = ("there" if asym.get("bone_conduction_only")
                     else f"at {bone_only} Hz")
            detail += (f" The {side} ear is not the poorer by air conduction "
                       f"{where}: an air-bone gap in the {other} ear hides the "
                       f"difference, and bone conduction shows the {side} "
                       "cochlea to be the worse.")
        conductive_other = asym.get("other_ear_conductive")
        if conductive_other:
            detail += (f" The {conductive_other['ear']} ear is the poorer by air "
                       f"conduction at {conductive_other['freqs']} Hz, but bone "
                       "conduction places that difference in its middle ear — a "
                       "conductive loss that needs otoscopy and tympanometry in "
                       "its own right.")
        action = ("Refer for ENT assessment; MRI with contrast is usually "
                  "indicated to exclude a vestibular schwannoma.")
        if assumed:
            detail += (f" Bone conduction was not measured at {assumed} Hz, so the "
                       "asymmetry there is assumed to be sensorineural.")
            action += (" Measure masked bone conduction where it can be tested "
                       "(to 4 kHz): if the asymmetry proves conductive, ENT / "
                       "otology assessment replaces imaging.")
        # The title names the type only when bone conduction showed it.
        title = ("Asymmetric sensorineural hearing loss — retrocochlear screen"
                 if asym.get("type_confirmed")
                 else "Asymmetric hearing loss — retrocochlear screen")
        return {"level": "urgent", "title": title, "ear": side,
                "detail": detail, "action": action}

    detail = (f"{reasons}, with the {side} ear outside normal limits. Bone "
              f"conduction at {asym['conductive_freqs']} Hz places the difference "
              f"in the middle ear: the {side} cochlea is within normal limits or "
              f"within {ASYM_PAIR_DB} dB of the {other}, so the air-bone gap "
              "carries the asymmetry.")
    if asym.get("untested_read_as_conductive"):
        detail += (f" Bone conduction was not measured at "
                   f"{asym['untested_read_as_conductive']} Hz; those frequencies "
                   "are read from the adjacent tested frequency.")
    action = (f"Refer for ENT / otology assessment of the {side} ear (otoscopy, "
              "tympanometry): a one-sided conductive loss is middle-ear disease "
              "and often medically or surgically treatable.")
    plan = masking.get(side) or {}
    unmasked = set(plan.get("bc_freqs") or []) & set(asym["conductive_freqs"])
    if plan.get("warning") and unmasked:
        # An unmasked bone-conduction threshold can belong to the other
        # cochlea, which is exactly how a one-sided sensorineural loss
        # masquerades as conductive.
        action += (f" Bone conduction in the {side} ear at {sorted(unmasked)} Hz "
                   "was not masked although masking was indicated: an unmasked "
                   "bone-conduction threshold can belong to the other cochlea. "
                   "Repeat it masked — if masked bone conduction is also "
                   "asymmetric, the loss is sensorineural and the retrocochlear "
                   "screen applies.")
    hidden = asym.get("other_ear_bc_not_measured") or []
    if hidden:
        action += (f" Bone conduction was not measured in the {other} ear at "
                   f"{hidden} Hz, where its air-conduction thresholds are poorer "
                   f"than the {side} cochlea by the asymmetry criterion: a "
                   f"sensorineural asymmetry in the {other} ear is not excluded. "
                   f"Measure masked bone conduction in the {other} ear — if its "
                   "cochlea is the worse, the retrocochlear screen applies.")
    return {"level": "urgent",
            "title": "Asymmetric conductive hearing loss — ENT / otology referral",
            "ear": side, "detail": detail, "action": action}


def safety_review(right, left, onset: str = "unknown",
                  baseline=None, transducer: str = None) -> dict:
    """All safety checks for a full test. ``right``/``left`` are EarData."""
    asym = asymmetry_check(right.ac, left.ac, right.bc, left.bc)
    sudden = {
        "right": sudden_loss_check(right.ac, right.bc, onset,
                                   baseline["right"].ac if baseline else None,
                                   opposite_ac=left.ac, opposite_bc=left.bc),
        "left": sudden_loss_check(left.ac, left.bc, onset,
                                  baseline["left"].ac if baseline else None,
                                  opposite_ac=right.ac, opposite_bc=right.bc),
    }
    from app.clinical.masking import masking_review

    # One review for both ears so the transducer, and therefore the crossover
    # point, is the same on each side of the same test.
    masking_bundle = masking_review(right, left, transducer)
    masking = {"right": masking_bundle["right"], "left": masking_bundle["left"]}

    alerts: List[dict] = []
    for side in ("right", "left"):
        s = sudden[side]
        if s["flag"]:
            alerts.append({
                "level": "emergency", "title": "Possible sudden sensorineural hearing loss",
                "ear": side, "detail": s["message"], "action": s["action"],
            })
        elif s["urgency"] == "ask":
            alerts.append({
                "level": "info", "title": "Onset not recorded",
                "ear": side, "detail": s["message"], "action": s["action"],
            })
    if asym["kind"]:
        alerts.append(_asymmetry_alert(asym, masking))
    for side in ("right", "left"):
        m = masking[side]
        # A dilemma only where the test ear's air conduction is within normal
        # limits (masking.masking_plan) cannot change the degree or type of
        # hearing — the cochlea there is normal whichever ear answered — so it
        # is reported, but does not displace the clinical next step as a
        # validity alert would.
        consequential = m.get("consequential_dilemma_freqs", m["dilemma_freqs"])
        if consequential:
            alerts.append({
                "level": "validity",
                "title": "Masking dilemma — these thresholds cannot be masked",
                "ear": side,
                "detail": (f"At {consequential} Hz the noise needed to cover "
                           "the crossed signal exceeds the level at which it "
                           "crosses back. A bilateral conductive loss with large "
                           "air-bone gaps leaves no usable masking level."),
                "action": "Repeat with insert earphones, which raise interaural "
                          "attenuation by 10-20 dB. If it persists, report these "
                          "thresholds as unmaskable rather than as measured.",
            })
        elif m["has_dilemma"]:
            alerts.append({
                "level": "info",
                "title": "Bone conduction unmaskable where hearing is normal",
                "ear": side,
                "detail": (f"At {m['dilemma_freqs']} Hz bone conduction cannot be "
                           "masked with this transducer: the occlusion effect "
                           "raises the noise needed above the level at which it "
                           "crosses back. Air conduction there is within normal "
                           f"limits (≤ {NORMAL_LIMIT_DB} dB HL), so the degree and "
                           "type of hearing do not depend on it — only the size of "
                           "the air-bone gap does."),
                "action": "If that gap matters (an abnormal tympanogram or "
                          "otoscopy), re-test bone conduction with the masking "
                          "noise delivered through an insert earphone, whose "
                          "occlusion effect is far smaller.",
            })
        if m["warning"]:
            alerts.append({
                "level": "validity", "title": "Masking indicated — results may be invalid",
                "ear": side, "detail": "; ".join(m["reasons"]), "action": m["message"],
            })

    sort_alerts(alerts)

    return {
        "alerts": alerts,
        "has_emergency": any(a["level"] == "emergency" for a in alerts),
        "has_urgent": any(a["level"] in ("emergency", "urgent") for a in alerts),
        "validity_warning": any(a["level"] == "validity" for a in alerts),
        "asymmetry": asym,
        "sudden": sudden,
        "masking": masking,
        "masking_review": masking_bundle,
    }
