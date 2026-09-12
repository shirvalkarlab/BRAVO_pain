"""PROBE 2 -- can the download itself be made small (always fresh, no cache), and is any cheap
REDCap freshness key available for a cross-request cache?

Reads only. Every timing is printed per round. The tidy pain-report table produced from a narrowed
download is compared cell-by-cell against the one produced from the full download.
"""
import datetime as dt
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
import logging                                                           # noqa: E402
logging.getLogger("urllib3").setLevel(logging.WARNING)

import pandas as pd                                                      # noqa: E402
import redcap                                                            # noqa: E402
from modules.Biomarkers.routines import redcap_client as RC              # noqa: E402
import json                                                              # noqa: E402

CFG = json.load(open("/usr/src/BRAVO/pt_config/RCS08_config.json"))
api_url, api_key = RC.get_redcap_credentials()
proj = redcap.Project(api_url, api_key)


def needed_fields(field_map):
    out = [field_map["timestamp_label"]]
    for v in (field_map.get("metric_labels") or {}).values():
        out.extend(v if isinstance(v, list) else [v])
    return list(dict.fromkeys(out))


FIELDS = needed_fields(CFG)
print("COLUMNS THE FIELD MAP ACTUALLY CONSUMES: %d (of 637 in the full export)" % len(FIELDS))
print("  ", FIELDS)
print("  record the field map keeps:", CFG.get("pt"), "| instrument:", CFG.get("instruments"))


def timed(label, fn, rounds=3):
    outs, ts = [], []
    for _ in range(rounds):
        t = time.perf_counter()
        o = fn()
        ts.append(time.perf_counter() - t)
        outs.append(o)
    shape = getattr(outs[-1], "shape", None) or len(outs[-1])
    print("  %-58s %s  mean %6.3f s   shape/len %s"
          % (label, " ".join("%6.3f" % x for x in ts), sum(ts) / len(ts), shape))
    return outs[-1], ts


print("\nDOWNLOAD SHAPES AND TIMES (3 rounds each)")
full, t_full = timed("full export, as it runs today", lambda: proj.export_records(
    format_type="df", export_checkbox_labels=True, export_survey_fields=True))
nar_f, t_narf = timed("narrowed to the columns the field map consumes",
                      lambda: proj.export_records(
                          format_type="df", export_checkbox_labels=True,
                          export_survey_fields=True, fields=FIELDS))
nar_r, t_narr = timed("narrowed to columns AND to this one record",
                      lambda: proj.export_records(
                          format_type="df", export_checkbox_labels=True,
                          export_survey_fields=True, fields=FIELDS,
                          records=[CFG["pt"]]))
nar_fo, t_narfo = timed("narrowed to the daily-survey instrument only",
                        lambda: proj.export_records(
                            format_type="df", export_checkbox_labels=True,
                            export_survey_fields=True, forms=CFG["instruments"],
                            records=[CFG["pt"]]))

print("\nDOES THE NARROWED DOWNLOAD PRODUCE THE IDENTICAL PAIN-REPORT TABLE?")
tidy_full = RC.process_redcap(full, CFG)
for label, raw in (("columns narrowed", nar_f), ("columns + record narrowed", nar_r),
                   ("instrument narrowed", nar_fo)):
    try:
        tidy = RC.process_redcap(raw, CFG)
    except Exception as e:
        print("  %-28s process_redcap FAILED %s: %s" % (label, type(e).__name__, e))
        continue
    same_cols = list(tidy_full.columns) == list(tidy.columns)
    same_n = len(tidy_full) == len(tidy)
    if same_cols and same_n:
        cmp = tidy_full.compare(tidy)
        ndiff = len(cmp)
    else:
        ndiff = "n/a"
    print("  %-28s rows %d vs %d | same columns %s | differing cells %s"
          % (label, len(tidy_full), len(tidy), same_cols, ndiff))

print("\nCHEAP FRESHNESS KEY CANDIDATES (3 rounds each)")


def try_key(label, fn, rounds=3):
    ts, out = [], None
    for _ in range(rounds):
        t = time.perf_counter()
        try:
            out = fn()
        except Exception as e:
            print("  %-58s FAILED %s: %s" % (label, type(e).__name__, str(e)[:140]))
            return None, None
        ts.append(time.perf_counter() - t)
    try:
        n = len(out)
    except Exception:
        n = "-"
    print("  %-58s %s  mean %6.3f s  n=%s"
          % (label, " ".join("%6.3f" % x for x in ts), sum(ts) / len(ts), n))
    return out, ts


now = dt.datetime.now()
log90, _ = try_key("export_logging(record edits, last 90 days)",
                   lambda: proj.export_logging(log_type="record",
                                               begin_time=now - dt.timedelta(days=90)))
if log90:
    print("      newest 3 rows:", [{k: r.get(k) for k in ("timestamp", "action", "record")}
                                   for r in log90[:3]])
log1, _ = try_key("export_logging(record edits, last 1 day)",
                  lambda: proj.export_logging(log_type="record",
                                              begin_time=now - dt.timedelta(days=1)))
if log1:
    print("      rows in the last day:", len(log1),
          [{k: r.get(k) for k in ("timestamp", "action", "record")} for r in log1[:3]])

ids, _ = try_key("export_records(fields=[record_id], json) -- row count",
                 lambda: proj.export_records(fields=[proj.def_field], format_type="json"))
tsonly, _ = try_key("export_records(fields=[timestamp only], json) -- row count",
                    lambda: proj.export_records(fields=[CFG["timestamp_label"]],
                                                format_type="json",
                                                records=[CFG["pt"]]))
if tsonly is not None:
    filled = [r for r in tsonly if r.get(CFG["timestamp_label"])]
    print("      rows %d, of which carry a timestamp %d, newest %s"
          % (len(tsonly), len(filled),
             max((r[CFG["timestamp_label"]] for r in filled), default=None)))

print("\nPROBE 2 DONE")
