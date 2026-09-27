"""Live proof (2026-09-27), decisions 340 (N-11, the sliding-window request default) and 341
(N-12, the deleted shuffle-test band inference). Store not touched. Writes ONE json line to stdout;
run the shell wrapper to keep warnings out of it.
"""
import sys, os, json, time
sys.path.insert(0, "/usr/src/BRAVO")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
os.environ.setdefault("BRAVO_PT_CONFIG_DIR", "/usr/src/BRAVO/pt_config")
import django; django.setup()
from modules.Biomarkers import bravo_service as bs

UID = "2e3c75c00d7f4f37b53a048d195f11da"


def flat(d, path=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{path}.{k}"))
    elif isinstance(d, list):
        out[path] = f"<list len {len(d)}>"
    else:
        out[path] = d
    return out


# Case TD: the time-domain branch -- where the deleted 1,000-shuffle _band_inference lived
# (decision 341). SlidingWindow does not gate this branch at all, so its value is irrelevant here.
t0 = time.time()
td = bs.run_for_participant({"ParticipantId": UID, "source": "timedomain",
                             "LabelMetric": "left_leg_vas"})
t_td = time.time() - t0

# Case PD-omit: the power-domain branch with the SlidingWindow field OMITTED -- exactly what the
# default itself controls (decision 340). Before: default True -> the train/test rolling detector
# runs. After: default False -> the single all-data fit (matching every real page request, which
# has always sent explicit false).
t0 = time.time()
pd_omit = bs.run_for_participant({"ParticipantId": UID, "source": "powerdomain",
                                  "LabelMetric": "left_leg_vas"})
t_pd_omit = time.time() - t0

# Case PD-explicit: the power-domain branch with SlidingWindow explicitly False -- the page's own
# real request. Must be identical before/after: proves today's live pages see no change at all.
t0 = time.time()
pd_explicit = bs.run_for_participant({"ParticipantId": UID, "source": "powerdomain",
                                      "LabelMetric": "left_leg_vas", "SlidingWindow": False})
t_pd_explicit = time.time() - t0

with open(sys.argv[1], "w") as f:
    json.dump({
        "t_td_s": t_td, "t_pd_omit_s": t_pd_omit, "t_pd_explicit_s": t_pd_explicit,
        "fields_td": flat(td.get("summary") or {}),
        "fields_pd_omit": flat(pd_omit.get("summary") or {}),
        "fields_pd_explicit": flat(pd_explicit.get("summary") or {}),
    }, f)
print("wrote", sys.argv[1])
