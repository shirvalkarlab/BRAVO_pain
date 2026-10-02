"""Export a read-only snapshot of the three tables the offline RL study trains and validates on.

Runs INSIDE the bravo-server container (it needs Django and the saved-results store). It reads the
stored entries only and writes nothing to the store or the database:

  visit_steps.csv     every parsed visit-sheet step, in-clinic and at-home, rated or not
                      (`clinic_pain.load_clinic_exposure`; no REDCap gap fill, so the training
                      ratings are the sheets' own and never the validation reports)
  chronic_epochs.csv  one row per long-term setting period since implant
                      (`adapter.exposure_epochs` on the stored `therapy_settings` stream)
  redcap_reports.csv  the newest stored REDCap snapshot (`redcap_reports`), with filing time in UTC

The output folder defaults to `/usr/src/BRAVO/_agent_bridge/_stim_rl_data` (gitignored; it holds
patient data and never enters the repository). The free-text `notes` column is dropped.

    python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 300 --wait 300 \
        "python3 -B modules/StimRL/export_snapshot.py"
"""
import hashlib
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/usr/src/BRAVO")
sys.path.insert(0, "/usr/src/BRAVO/modules")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")

UID = "2e3c75c00d7f4f37b53a048d195f11da"
OUT = os.environ.get("STIM_RL_EXPORT_DIR", "/usr/src/BRAVO/_agent_bridge/_stim_rl_data")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    import django
    django.setup()
    import pandas as pd
    from Server import models
    from modules.StimOptimizer import clinic_pain as CP, adapter as AD
    from modules.CacheStore import store as ST

    os.makedirs(OUT, exist_ok=True)
    P = models.Participant.find(uid=UID)
    manifest = {"uid": UID}

    steps, stamp, reason = CP.load_clinic_exposure(P)
    if steps is None:
        raise SystemExit(f"no stored visit steps ({reason})")
    steps = steps.drop(columns=[c for c in ("notes",) if c in steps.columns])
    from modules.StimOptimizer import stage1_openloop as S1
    # The Left contact in the clinic sheet's notation, by the module's one definition; the policy
    # conditions on it so no recommendation pools two electrodes (decision 74).
    steps["left_contact"] = [S1.left_contact_label(c, a) for c, a in
                             zip(steps["contacts_raw"], steps["amp_mA_Left"])]
    p = os.path.join(OUT, "visit_steps.csv")
    steps.to_csv(p, index=False)
    manifest["visit_steps"] = {"rows": int(len(steps)), "sha256": _sha(p),
                               "rule_version": (stamp or {}).get("rule_version")}

    stream, _ = ST.load_newest(AD.THERAPY_SETTINGS_KIND, UID)
    if stream is None:
        raise SystemExit("no stored therapy_settings stream")
    ep = AD.exposure_epochs(stream)
    ep["left_contact"] = [S1.left_contact_label(c, a) for c, a in
                          zip(ep["cathode_Left"], ep["amp_mA_Left"])]
    p = os.path.join(OUT, "chronic_epochs.csv")
    ep.to_csv(p, index=False)
    manifest["chronic_epochs"] = {"rows": int(len(ep)), "sha256": _sha(p),
                                  "rates_agree_across_sides": bool(ep.attrs.get("rates_agree_across_sides"))}

    rep, rstamp = ST.load_newest("redcap_reports", UID)
    if rep is None:
        raise SystemExit("no stored redcap_reports snapshot")
    from modules.Biomarkers import bravo_service as BS
    rep = rep.copy()
    rep["t_utc"] = pd.to_datetime(BS._pro_times_utc_series(rep), utc=True).values
    p = os.path.join(OUT, "redcap_reports.csv")
    rep.to_csv(p, index=False)
    manifest["redcap_reports"] = {"rows": int(len(rep)), "sha256": _sha(p),
                                  "written_at": str((rstamp or {}).get("written_at")
                                                    or (rstamp or {}).get("created"))}

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, default=str)
    print(json.dumps(manifest, indent=1, default=str))
    print("columns visit_steps:", list(steps.columns))
    print("columns chronic_epochs:", list(ep.columns))
    print("columns redcap_reports:", list(rep.columns))


if __name__ == "__main__":
    main()
