"""How far a band stands above the smooth background of the device's own PSDs (item 7b, the PI,
2026-10-18: "do all"; the preference for a band with a measurable peak).

WHAT IS MEASURED. Every device PSD stored for the participant (the montage and electrode-survey
PSDs, the signal-check PSDs and the run-unknown survey PSDs, exactly as the device exported them,
in microvolts peak, no PSD of our own) is fitted with a smooth falling background,
``a * f**-b + c``, between 2 and 90 Hz with the bins from 53 to 62 Hz left out (the mains line
and the 55 Hz stimulation rate). The fit is weighted by the PSD's own value (``sigma = p``, so
every bin counts in proportion, not the largest ones), then refitted three times keeping only
the bins at or below 1.5 times the previous fit, so a peak does not pull the background up to
itself. A band's ratio on one PSD is the mean of the PSD's bins inside the band divided by the
mean of the fitted background over the same bins. A ratio of 1.0 means no peak; 1.25 means the
band sits a quarter above the background. The source fitting method is retained; participant-specific empirical findings are
private evidence, not application defaults.

WHAT A BAND IS. The device's band: the centre plus or minus 2.5 Hz (5 Hz wide, D10), edges
included. Ratios are kept per contact pair and side (never pooled across electrodes, rule 13), per
band centre on the 1 Hz grid the band grid uses, as the MEDIAN over that pair's PSDs, with the
count beside it. PSDs the device itself flagged as carrying an artefact (``ArtifactStatus`` other
than ``ARTIFACT_NOT_PRESENT``) are left out and counted, and so is every PSD the fit cannot be
made on.

WHAT IT IS USED FOR, and what it must never do. It is evidence beside a band on the Closed-Loop
page, and a TIE-BREAK between candidates that are otherwise equal (`tie_break_key`): a band with
a larger ratio is preferred only among bands whose verdict and every other comparison key are the
same. It never changes a verdict, never refuses and never licenses (the PI's instruction:
"used only as a tie-break preference between otherwise-equal candidates").

Pure numpy and scipy here; the Django read (`psds_for_participant`) imports inside itself.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

KIND = "closed_loop_peak_above_background"
RULE_VERSION = "v1_aperiodic_fit_2_90hz_no_53_62_three_refits_device_band_edges_inclusive"

#: The fit's frequency range and the bins left out of it (mains and the 55 Hz stimulation rate).
FIT_RANGE_HZ = (2.0, 90.0)
FIT_EXCLUDE_HZ = (53.0, 62.0)
#: A bin above this multiple of the previous fit is treated as a peak and left out of the refit.
REFIT_PEAK_FACTOR = 1.5
REFITS = 3
#: Fewer bins than this left in the fit and the refitting stops (the script's own rule).
MIN_FIT_BINS = 15
MIN_PSD_BINS = 20
#: The device band: centre +- 2.5 Hz (D10, `constraints.BAND_WIDTH_NOMINAL_HZ`).
BAND_HALF_HZ = 2.5
#: The band centres the ratio is kept for: the band grid's 1 Hz centres whose band fits inside the
#: fitted range.
CENTRES_HZ: Tuple[float, ...] = tuple(float(c) + 0.5 for c in range(4, 87))
#: The device's own "no artefact" verdict; any other status leaves the PSD out.
CLEAN_STATUS = "ARTIFACT_NOT_PRESENT"
#: The stored PSD recording types read, and where each keeps its PSDs.
PSD_TYPES = ("MedtronicBrainSenseSurvey", "MedtronicBaselineMontages",
             "MedtronicStimulationMontages", "MedtronicSurveyPSD", "MedtronicSignalCheckPSD")


def background(f, a, b, c):
    """The smooth falling background, ``a * f**-b + c``."""
    return a * np.power(f, -b) + c


def fit_background(f, p) -> Optional[Tuple[float, float, float]]:
    """``(a, b, c)`` of the background fitted to one PSD, or None when it cannot be fitted."""
    from scipy.optimize import curve_fit
    try:
        f = np.atleast_1d(np.asarray(f, dtype=float))
        p = np.atleast_1d(np.asarray(p, dtype=float))
    except (TypeError, ValueError):
        return None
    if (f.ndim != 1 or p.ndim != 1 or f.size < MIN_PSD_BINS or f.size != p.size
            or not np.all(np.isfinite(f)) or not np.all(np.isfinite(p)) or p.max() <= 0):
        return None
    m = (f >= FIT_RANGE_HZ[0]) & (f <= FIT_RANGE_HZ[1]) & \
        ~((f >= FIT_EXCLUDE_HZ[0]) & (f <= FIT_EXCLUDE_HZ[1]))
    ff, pp = f[m], p[m]
    if ff.size < MIN_FIT_BINS or np.any(pp <= 0):
        return None
    try:
        keep = np.ones(ff.size, dtype=bool)
        prm = None
        for _ in range(REFITS):
            prm, _cov = curve_fit(background, ff[keep], pp[keep],
                                  p0=[pp[0] * 2.0, 1.0, pp[-5:].mean() * 0.5], sigma=pp[keep],
                                  bounds=([0.0, 0.0, 0.0], [np.inf, 4.0, np.inf]), maxfev=5000)
            keep = pp <= REFIT_PEAK_FACTOR * background(ff, *prm)
            if keep.sum() < MIN_FIT_BINS:
                break
    except Exception:                                       # noqa: BLE001 - no fit is an answer
        return None
    if prm is None or not np.all(np.isfinite(prm)):
        return None
    return float(prm[0]), float(prm[1]), float(prm[2])


def band_ratio(f, p, prm, centre_hz, *, half_hz=BAND_HALF_HZ) -> Optional[float]:
    """The PSD's mean over the device band's bins divided by the background's mean over them."""
    f = np.asarray(f, dtype=float)
    p = np.asarray(p, dtype=float)
    b = (f >= float(centre_hz) - half_hz) & (f <= float(centre_hz) + half_hz)
    if not b.any() or prm is None:
        return None
    bg = float(np.mean(background(f[b], *prm)))
    if not np.isfinite(bg) or bg <= 0:
        return None
    return float(np.mean(p[b]) / bg)


def _pair_key(channel, hemisphere=None) -> Optional[str]:
    """The canonical contact pair and side, ``ZERO_THREE_LEFT``, from either spelling the device
    writes (``SensingElectrodeConfigDef.ZERO_AND_THREE`` with ``HemisphereLocationDef.Left``, or a
    streaming name already carrying the side). Segmented and single-electrode names keep their own
    spelling, so they never merge with a ring pair."""
    if channel is None:
        return None
    u = str(channel).split(".")[-1].upper().replace("_AND_", "_")
    if u.endswith("_RING"):
        u = u[:-len("_RING")]
    if u.endswith("_LEFT") or u.endswith("_RIGHT"):
        return u
    side = str(hemisphere or "").split(".")[-1].upper()
    if side not in ("LEFT", "RIGHT"):
        return None
    return f"{u}_{side}"


def ratios_from_psds(psds: Iterable[Dict[str, Any]],
                     centres: Sequence[float] = CENTRES_HZ) -> Dict[str, Any]:
    """Per contact pair and side, per band centre: the median ratio over that pair's PSDs and the
    count. ``psds`` yields dicts with ``channel``, ``hemisphere`` (may be None when the channel
    carries the side), ``f``, ``p`` and ``status`` (the device's ArtifactStatus, or None)."""
    per: Dict[str, List[np.ndarray]] = {}
    counts = {"psds": 0, "flagged_by_device": 0, "no_fit": 0, "no_pair": 0, "used": 0}
    cs = np.asarray(centres, dtype=float)
    for d in psds:
        counts["psds"] += 1
        key = _pair_key(d.get("channel"), d.get("hemisphere"))
        if key is None:
            counts["no_pair"] += 1
            continue
        st = d.get("status")
        if st is not None and str(st).split(".")[-1] != CLEAN_STATUS:
            counts["flagged_by_device"] += 1
            continue
        prm = fit_background(d.get("f"), d.get("p"))
        if prm is None:
            counts["no_fit"] += 1
            continue
        f = np.asarray(d["f"], dtype=float)
        p = np.asarray(d["p"], dtype=float)
        row = np.array([np.nan if (r := band_ratio(f, p, prm, c)) is None else r for c in cs])
        per.setdefault(key, []).append(row)
        counts["used"] += 1
    out: Dict[str, Any] = {}
    for key, rows in sorted(per.items()):
        a = np.vstack(rows)
        n = np.isfinite(a).sum(axis=0)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)      # an all-empty centre is n = 0
            med = np.nanmedian(a, axis=0)
        out[key] = {f"{c:g}": {"median_ratio": (float(med[i]) if n[i] else None), "n_psds": int(n[i])}
                    for i, c in enumerate(cs)}
    return {"rule_version": RULE_VERSION, "by_pair": out, "counts": counts,
            "centres_hz": [float(c) for c in cs]}


def for_band(table: Optional[Dict[str, Any]], channel, centre_hz) -> Dict[str, Any]:
    """The chosen band's entry: its median ratio on its own contact pair, the count, and what it is
    for. ``available`` False, with the reason, when the pair or the centre has no PSD."""
    out = {"available": False, "channel": str(channel), "center_hz": None, "median_ratio": None,
           "n_psds": 0, "use": "tie-break only between otherwise-equal candidates; never a verdict",
           "rule_version": RULE_VERSION}
    if not table or not table.get("by_pair"):
        out["reason"] = "no stored device PSD could be fitted for this participant"
        return out
    key = _pair_key(channel)
    per = (table.get("by_pair") or {}).get(key or "")
    if not per:
        out["reason"] = f"no device PSD on {channel} could be fitted"
        return out
    try:
        c = float(centre_hz)
    except (TypeError, ValueError):
        out["reason"] = "the band has no centre"
        return out
    cs = np.asarray([float(k) for k in per], dtype=float)
    if not np.isfinite(c) or not cs.size or float(np.min(np.abs(cs - c))) > 0.25:
        out["reason"] = f"{c:g} Hz is outside the centres the ratio is kept for"
        return out
    k = list(per)[int(np.argmin(np.abs(cs - c)))]
    ent = per[k]
    out.update({"center_hz": float(k), "median_ratio": ent.get("median_ratio"),
                "n_psds": int(ent.get("n_psds") or 0),
                "available": ent.get("median_ratio") is not None})
    if not out["available"]:
        out["reason"] = f"no device PSD on {channel} has a bin inside {float(k):g} +- 2.5 Hz"
    return out


def tie_break_key(candidate: Dict[str, Any], *, equal_on: Sequence[str]) -> Tuple:
    """A sort key that orders candidates by ``equal_on`` first, exactly as given, and only then by
    the larger peak ratio (a candidate with no ratio last among its equals). Because every key in
    ``equal_on`` comes first, the ratio can reorder only candidates that tie on all of them: it
    cannot move a refused band above an allowed one, or change any verdict."""
    head = tuple(candidate.get(k) for k in equal_on)
    r = candidate.get("peak_ratio")
    try:
        r = float(r)
        ok = np.isfinite(r)
    except (TypeError, ValueError):
        ok = False
    return head + ((0, -r) if ok else (1, 0.0),)


# ---------------------------------------------------------------------------------------------
# The stored PSDs, read from the database (Django inside)
# ---------------------------------------------------------------------------------------------
def _as_list(d):
    return d if isinstance(d, list) else [d]


def psds_from_decoded(rec_type: str, decoded) -> List[Dict[str, Any]]:
    """The device PSDs in one decoded recording, in the shape `ratios_from_psds` reads."""
    out = []
    for x in _as_list(decoded):
        if not isinstance(x, dict):
            continue
        desc = x.get("Descriptor") or {}
        if rec_type == "MedtronicSignalCheckPSD":
            sc = desc.get("SignalCheck") or {}
            out.append({"channel": sc.get("Channel"), "hemisphere": None,
                        "f": sc.get("SignalFrequencies"), "p": sc.get("SignalPsdValues"),
                        "status": sc.get("ArtifactStatus")})
            continue
        for b in desc.get("MedtronicPSD") or []:
            if not isinstance(b, dict):
                continue
            f = b.get("LFPFrequency") if b.get("LFPFrequency") is not None else b.get("LFPFrequencyinHertz")
            p = b.get("LFPMagnitude") if b.get("LFPMagnitude") is not None else b.get("LFPMagnitudeinMicroVoltPeak")
            out.append({"channel": b.get("SensingElectrodes"), "hemisphere": b.get("Hemisphere"),
                        "f": f, "p": p, "status": b.get("ArtifactStatus")})
    return out


def psds_for_participant(participant, *, threads: int = 16) -> Tuple[List[Dict[str, Any]], int]:
    """Every stored device PSD of the participant (``PSD_TYPES``), and how many recordings could
    not be decoded. Reads only; writes nothing."""
    from concurrent.futures import ThreadPoolExecutor
    from Server import models as _m
    try:
        from modules import Database as _db
    except ImportError:                                   # pragma: no cover - host spelling
        import Database as _db
    rows = list(_m.Recording.objects.filter(source__owner=participant, type__in=PSD_TYPES))

    def one(r):
        try:
            return r.type, _db.loadSourceFile(r.pointer, r.hashed)
        except Exception:                                 # noqa: BLE001 - counted, not fatal
            return r.type, None

    psds, bad = [], 0
    with ThreadPoolExecutor(max(1, int(threads))) as ex:
        for typ, d in ex.map(one, rows):
            if d is None:
                bad += 1
                continue
            psds.extend(psds_from_decoded(typ, d))
    return psds, bad
