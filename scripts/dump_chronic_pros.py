#!/usr/bin/env python3
"""Dump the REAL chronic PRO frames the biomarker pipeline uses, for offline analysis.

Mirrors `bravo_service.run_for_participant`'s data-prep (PRO pull + per-sample
`cv_df` build) but writes the frames to disk instead of running the detector. The
binarization methodology study runs against these exports (the long chronic daily
series), NOT the 2-week stage-0 sEEG tidy file.

Run INSIDE the container (it needs the Django DB + REDCap env):

    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 \
        python3 -W ignore manage.py shell -c \
        "exec(open('/usr/src/BRAVO/../scripts/dump_chronic_pros.py').read())"

...or, simpler, copy this file in and `exec(open(...).read())` from a shell. It
writes to OUT_DIR (default /usr/src/BRAVO/_pro_dump, which is the live-mounted
repo's BRAVO dir — adjust to a path that maps to ~/dev/BRAVO_pain on the host).
"""
import os
import json
import numpy as np
import pandas as pd

from modules.Biomarkers import bravo_service, adapter
from Server import models

PARTICIPANT_NAME = os.environ.get("DUMP_PARTICIPANT", "RCS08")
# Default to a host-visible location: the repo is live-mounted at /usr/src/BRAVO
# (-> ~/dev/BRAVO_pain/BRAVO). Write one level up so it lands in ~/dev/BRAVO_pain/_pro_dump.
# /usr/src/BRAVO is the live-mounted ./BRAVO dir, so this lands at
# ~/dev/BRAVO_pain/BRAVO/_pro_dump on the host (readable from the sandbox grant).
OUT_DIR = os.environ.get("DUMP_OUT", "/usr/src/BRAVO/_pro_dump")
os.makedirs(OUT_DIR, exist_ok=True)


def _find_participant(name):
    p = models.Participant.find(name=name)
    if p is None:
        raise SystemExit(f"Participant {name!r} not found")
    return p


def main():
    p = _find_participant(PARTICIPANT_NAME)
    req = {"ParticipantId": p.uid, "source": "both"}

    # --- replicate run_for_participant's PRO load ---
    pro_df = bravo_service._load_pros(req, p)
    if pro_df is None or len(pro_df) == 0:
        raise SystemExit("No PRO data returned (REDCAP_API_URL/TOKEN set?)")

    pro_path = os.path.join(OUT_DIR, f"{PARTICIPANT_NAME}_chronic_pro_df.csv")
    pro_df.to_csv(pro_path, index=False)

    # --- replicate the power-domain (chronic) recording load so cv_df is the real one ---
    chronic_list = bravo_service._load_recordings(p.uid, bravo_service.CHRONIC_TYPES)
    powerdomain_list = bravo_service._load_recordings(p.uid, bravo_service.POWERDOMAIN_TYPES)
    for c in chronic_list:
        if isinstance(c, dict):
            c.setdefault("Source", "chronic")
    power_list = list(chronic_list) + adapter.bravo_powerdomain_to_chronic_like(powerdomain_list)
    chronic = power_list if power_list else None

    manifest = {
        "participant": PARTICIPANT_NAME,
        "uid": p.uid,
        "pro_df_path": pro_path,
        "pro_df_shape": list(pro_df.shape),
        "pro_df_columns": list(pro_df.columns),
        "has_chronic": chronic is not None,
        "cv_dfs": {},
    }

    # Build the per-sample labeled frame for each candidate metric (the binary `pain_level`
    # the detector consumes), exactly as _compute_analytics would, so we can study how each
    # binarization strategy carves the SAME aligned series.
    if chronic is not None:
        for metric in ["nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum"]:
            if metric not in pro_df.columns:
                continue
            try:
                cv = adapter.bravo_chronic_to_lfp_df(
                    chronic, pro_df, label_metric=metric, label_strategy="kmeans",
                    kmeans_features=(metric,),
                )
                cp = os.path.join(OUT_DIR, f"{PARTICIPANT_NAME}_cv_df_{metric}.csv")
                cv.to_csv(cp, index=False)
                manifest["cv_dfs"][metric] = {"path": cp, "shape": list(cv.shape)}
            except Exception as e:  # noqa: BLE001
                manifest["cv_dfs"][metric] = {"error": repr(e)}

        # Composite (MPQ + left-leg VAS), the notebook's 2-D KMeans labeler.
        pro2, lm, kf = bravo_service._resolve_biomarker_metric(
            {"LabelMetric": "composite_mpq_leftleg"}, pro_df)
        try:
            cv = adapter.bravo_chronic_to_lfp_df(
                chronic, pro2, label_metric=lm, label_strategy="kmeans", kmeans_features=kf)
            cp = os.path.join(OUT_DIR, f"{PARTICIPANT_NAME}_cv_df_composite.csv")
            cv.to_csv(cp, index=False)
            manifest["cv_dfs"]["composite"] = {"path": cp, "shape": list(cv.shape),
                                               "kmeans_features": list(kf)}
        except Exception as e:  # noqa: BLE001
            manifest["cv_dfs"]["composite"] = {"error": repr(e)}

    mpath = os.path.join(OUT_DIR, f"{PARTICIPANT_NAME}_dump_manifest.json")
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    print("WROTE:", mpath)
    print(json.dumps(manifest, indent=2, default=str))


main()
