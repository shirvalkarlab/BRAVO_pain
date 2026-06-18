#!/usr/bin/env python3
"""Provenance / label-consistency audit for a Biomarkers `queryBiomarkerAnalysis` payload.

The Biomarkers report card has many panels whose TITLES, ANNOTATIONS, and CAPTIONS make claims about
the data they show — which contacts, which sensing frequency, how many curves, what the bar means.
Several visible bugs have been label-vs-data mismatches (e.g. a ROC annotated "@ 28.3 Hz" for contacts
that recorded at 23.4/26.4 Hz; "3 frequencies" listed over "mean of 2 contacts"). Those are checkable
WITHOUT rendering pixels: the response JSON that drives the frontend contains both the data and enough
structure to know what each panel will assert.

This script loads such a payload (the JSON returned by POST /api/queryBiomarkerAnalysis, or a saved
copy) and reports inconsistencies a reviewer would otherwise have to catch one screenshot at a time:

  - ROC: per-hemisphere mean is over contacts that actually have an ROC; the frequency set reported
    for the panel must match the DRAWN contacts (single-class contacts are dropped -> must not appear
    in the frequency list or the contact count).
  - Provenance frequencies must come from `recorded_powers[*].center_hz` (per-contact streaming band),
    never from `chronic_center_hz` (the chronic 10-min trend's separate fixed frequency).
  - Honest-performance swarm: dot count per metric = contacts with a FINITE value for that metric.
  - per_channel keys partition cleanly into hemisphere aggregates vs bipolar contacts.
  - Sliding-window panel visibility vs the all-data window.
  - Generic: any contact label whose hemisphere can't be parsed; any AUC~1.0 batch-artifact contacts.

Usage:
    python audit_biomarker_payload.py path/to/payload.json [--json]

Exit code is 0 if no ERROR-level findings, 1 otherwise (so it can gate CI). `--json` emits a machine
-readable report instead of text.
"""
import argparse
import json
import sys


def _num(x):
    return isinstance(x, (int, float)) and x == x  # finite-ish (not None, not NaN)


def _hemi_of(label):
    s = str(label or "").strip()
    if not s:
        return None
    if "hemisphere" in s.lower():
        return "Left" if s.lower().startswith("left") else ("Right" if s.lower().startswith("right") else None)
    f = s[:1].upper()
    return "Left" if f == "L" else ("Right" if f == "R" else None)


def _kind_of(label):
    return "aggregate" if "hemisphere" in str(label or "").lower() else "contact"


def _has_roc(entry):
    r = (entry or {}).get("roc")
    return bool(r and r.get("fpr") and len(r["fpr"]) >= 2)


def audit(payload):
    """Return a list of findings: {level, panel, message}."""
    findings = []

    def add(level, panel, message):
        findings.append({"level": level, "panel": panel, "message": message})

    analytics = payload.get("analytics") or {}
    pdr = analytics.get("powerdomain") or payload.get("powerdomain") or {}
    per_channel = pdr.get("per_channel") or {}
    recorded = payload.get("recorded_powers") or []
    chronic_hz = pdr.get("chronic_center_hz") or {}

    # --- recorded_powers: per-contact center frequencies (the provenance source of truth) ----------
    rec_hz = {}
    for p in recorded:
        if p and p.get("label") is not None and _num(p.get("center_hz")):
            rec_hz[str(p["label"]).strip()] = float(p["center_hz"])
    if not rec_hz:
        add("WARN", "recorded_powers",
            "No recorded_powers center frequencies - provenance will fall back to chronic_center_hz "
            "(the chronic-trend frequency), which is NOT the per-contact streaming band.")

    # --- per_channel partition --------------------------------------------------------------------
    contacts, aggregates, unparsed = [], [], []
    for k in per_channel:
        (aggregates if _kind_of(k) == "aggregate" else contacts).append(k)
        if _hemi_of(k) is None:
            unparsed.append(k)
    for k in unparsed:
        add("ERROR", "per_channel", f"Contact/aggregate key '{k}' has an unparseable hemisphere.")

    by_hemi = {"Left": [], "Right": []}
    for k in contacts:
        h = _hemi_of(k)
        if h in by_hemi:
            by_hemi[h].append(k)

    # --- ROC per-hemisphere: drawn contacts vs reported frequencies -------------------------------
    for h, keys in by_hemi.items():
        if not keys:
            continue
        drawn = [k for k in keys if _has_roc(per_channel[k])]
        dropped = [k for k in keys if not _has_roc(per_channel[k])]
        hz_all = sorted({round(rec_hz[k], 1) for k in keys if k in rec_hz})
        hz_drawn = sorted({round(rec_hz[k], 1) for k in drawn if k in rec_hz})
        if dropped and hz_all != hz_drawn:
            add("ERROR", "ROC",
                f"{h}: {len(drawn)} contact(s) drawn ({drawn}) but recorded-frequency set spans all "
                f"{len(keys)} ({hz_all} Hz). Panel must report only DRAWN frequencies {hz_drawn} Hz; "
                f"dropped (single-class) contacts {dropped} must not be listed.")
        if 0 < len(drawn) < 2:
            add("INFO", "ROC", f"{h}: only {len(drawn)} contact has an ROC - no mean curve drawn (expected).")

    # --- Frequency provenance must not equal chronic where they differ ----------------------------
    for h in ("Left", "Right"):
        ck = f"{h}Hemisphere"
        chz = chronic_hz.get(ck)
        rec_for_h = sorted({round(rec_hz[k], 1) for k in by_hemi.get(h, []) if k in rec_hz})
        if _num(chz) and rec_for_h and round(chz, 1) not in rec_for_h:
            add("INFO", "provenance",
                f"{h}: chronic_center_hz={chz:.1f} Hz differs from recorded contact bands {rec_for_h} Hz "
                f"- provenance strings MUST use the recorded bands, not the chronic value.")

    # --- Honest-performance swarm: dot count per metric -------------------------------------------
    for field, bar in (("auc_in_sample", "In-sample AUC"), ("balanced_accuracy", "CV balanced accuracy")):
        dotted = [k for k in contacts if _num((per_channel[k].get("summary") or {}).get(field))]
        with_summary = [k for k in contacts if per_channel[k].get("summary")]
        if with_summary and len(dotted) != len(with_summary):
            add("INFO", "honest-swarm",
                f"'{bar}' bar: {len(dotted)} of {len(with_summary)} contacts have a finite {field}; the "
                f"caption count must be the union of dotted contacts, not the contact total.")

    # --- AUC~1.0 batch-artifact contacts ----------------------------------------------------------
    near_one = [k for k in contacts
                if _num((per_channel[k].get("summary") or {}).get("auc_in_sample"))
                and per_channel[k]["summary"]["auc_in_sample"] >= 0.999]
    if near_one:
        add("WARN", "ROC/honest",
            f"Contacts with in-sample AUC~1.0 (likely batch/scale artifact, not real discrimination): {near_one}. "
            "Confirm the pooled-warning is surfaced.")

    # --- Sliding-window panel visibility ----------------------------------------------------------
    sw = pdr.get("sliding_window")
    windows = sw.get("windows") if isinstance(sw, dict) else (sw if isinstance(sw, list) else [])
    windows = windows or []
    all_data_only = bool(windows) and all(w.get("all_data") for w in windows)
    if all_data_only:
        add("INFO", "sliding-window",
            "Only an all-data window present (sliding OFF) - the over-time panel should be SUPPRESSED, "
            "but the contact/hemisphere toggle must remain.")

    # --- Pooled-target warning --------------------------------------------------------------------
    if pdr.get("powerdomain_pooled_warning") or payload.get("powerdomain_pooled_warning"):
        add("INFO", "power-domain",
            "powerdomain_pooled_warning present - the power-domain timeline/threshold pools >1 target; "
            "labels must say 'pooled across N contacts', not name a single frequency.")

    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("payload", help="Path to the queryBiomarkerAnalysis response JSON.")
    ap.add_argument("--json", action="store_true", help="Emit a JSON report instead of text.")
    args = ap.parse_args()

    with open(args.payload) as fh:
        payload = json.load(fh)

    findings = audit(payload)
    errors = [f for f in findings if f["level"] == "ERROR"]

    if args.json:
        print(json.dumps({"n_findings": len(findings), "n_errors": len(errors), "findings": findings}, indent=2))
    else:
        if not findings:
            print("OK - no provenance/label inconsistencies found.")
        else:
            order = {"ERROR": 0, "WARN": 1, "INFO": 2}
            for f in sorted(findings, key=lambda x: order.get(x["level"], 9)):
                print(f"[{f['level']:5s}] {f['panel']:14s} {f['message']}")
            print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} advisory.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
