"""PROBE 1 -- how many times does one band-by-length-of-signal sweep request pull the pain
reports from REDCap, and how does that 1.7 s split between the download and the field mapping?

Nothing here changes any file. It counts real calls on the real record and times the two halves
separately, plus it tries every cheap freshness key REDCap might offer.
"""
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, "/usr/src/BRAVO")
sys.path.insert(0, "/usr/src/BRAVO/modules")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
import django                                                            # noqa: E402
django.setup()

from modules.Biomarkers import bravo_service as B                        # noqa: E402
from modules.Biomarkers.routines import redcap_client as RC              # noqa: E402
from Server import models                                                # noqa: E402

UID = "2e3c75c00d7f4f37b53a048d195f11da"
P = models.Participant.find(uid=UID)
REQ = {"ParticipantId": UID, "BandTimeSweep": "1", "SweepMetric": "nrs",
       "LabelStrategy": "tertile", "PercentileLow": 33.3, "PercentileHigh": 66.7,
       "MatchToleranceMin": 60, "AllowWindowReuse": ""}

# ---------------------------------------------------------------- call counting
counts = {"pull_redcap": 0, "process_redcap": 0, "get_redcap_credentials": 0,
          "_load_pros": 0, "_load_pros_raw": 0}
secs = {k: 0.0 for k in counts}
_orig = {}


def wrap(mod, name, key):
    fn = getattr(mod, name)
    _orig[(mod, name)] = fn

    def inner(*a, **kw):
        counts[key] += 1
        t = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            secs[key] += time.perf_counter() - t
    setattr(mod, name, inner)


for nm in ("pull_redcap", "process_redcap", "get_redcap_credentials"):
    wrap(RC, nm, nm)
for nm in ("_load_pros", "_load_pros_raw"):
    wrap(B, nm, nm)

print("CALL COUNT DURING ONE FULL SWEEP REQUEST (all sensing contact pairs)")
t0 = time.perf_counter()
got = B.run_for_participant(dict(REQ))
wall = time.perf_counter() - t0
pairs = sorted((got.get("band_time_sweep") or {}).keys())
print("  request wall %.3f s | sensing contact pairs returned %d %s"
      % (wall, len(pairs), pairs))
print("  message:", got.get("message"))
for k in counts:
    print("  %-24s calls %2d   total %7.3f s" % (k, counts[k], secs[k]))

for (mod, name), fn in _orig.items():
    setattr(mod, name, fn)

# ------------------------------------------------- download vs mapping, separately
print("\nDOWNLOAD versus FIELD MAPPING, timed separately (3 rounds)")
field_map = B._resolve_field_map(dict(REQ), P)
print("  field map resolved from pt_config:", bool(field_map),
      "| instruments:", (field_map or {}).get("instruments"),
      "| metric keys:", sorted(((field_map or {}).get("metric_labels") or {}).keys()))
for r in range(3):
    t = time.perf_counter()
    raw = RC.pull_redcap()
    t_dl = time.perf_counter() - t
    t = time.perf_counter()
    tidy = RC.process_redcap(raw, field_map)
    t_map = time.perf_counter() - t
    print("  round %d: download %6.3f s (raw rows %d x cols %d) | mapping %6.3f s "
          "(tidy rows %d) | total %6.3f s"
          % (r + 1, t_dl, len(raw), len(raw.columns), t_map, len(tidy), t_dl + t_map))

# ------------------------------------------------- cheap freshness key candidates
print("\nIS THERE A CHEAP FRESHNESS KEY? (each timed; a key must be much cheaper than 1.7 s)")
import redcap                                                            # noqa: E402
api_url, api_key = RC.get_redcap_credentials()
t = time.perf_counter()
proj = redcap.Project(api_url, api_key)
print("  redcap.Project() construction                     %6.3f s" % (time.perf_counter() - t))

def try_key(label, fn):
    t = time.perf_counter()
    try:
        out = fn()
    except Exception as e:
        print("  %-49s FAILED  %s: %s" % (label, type(e).__name__, str(e)[:160]))
        return None
    dt = time.perf_counter() - t
    try:
        n = len(out)
    except Exception:
        n = "-"
    print("  %-49s %6.3f s  (n=%s)" % (label, dt, n))
    return out

info = try_key("export_project_info()", lambda: proj.export_project_info())
if isinstance(info, dict):
    print("      project info keys:", sorted(info.keys()))

ids = try_key("export_records(fields=[record_id], format=json)",
              lambda: proj.export_records(fields=[proj.def_field], format_type="json"))

log_all = try_key("export_logging(begin_time=2 days ago)",
                  lambda: proj.export_logging(
                      begin_time=time.strftime("%Y-%m-%d %H:%M",
                                               time.localtime(time.time() - 2 * 86400))))
if isinstance(log_all, list) and log_all:
    print("      newest log row:", {k: log_all[0].get(k) for k in
                                    ("timestamp", "action", "record", "username")})

log_wide = try_key("export_logging(begin_time=90 days ago)",
                   lambda: proj.export_logging(
                       begin_time=time.strftime("%Y-%m-%d %H:%M",
                                                time.localtime(time.time() - 90 * 86400))))

log_rec = try_key("export_logging(log_type=record, 90 days)",
                  lambda: proj.export_logging(
                      log_type="record",
                      begin_time=time.strftime("%Y-%m-%d %H:%M",
                                               time.localtime(time.time() - 90 * 86400))))

# The tidy timestamp column itself: a max() over the reports is only knowable AFTER a full
# download, so it cannot be a freshness key -- recorded here to show it was considered.
print("\nPROBE 1 DONE")
