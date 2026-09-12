# Wiring the "does the band behave the same under every setting" answer into the closed-loop report

Written for the PI to apply. Nothing in `adapter.py`, `pipeline.py`, `edges.py`, `types.py` or any
existing React file has been touched by the session that wrote `stability.py`, because those files
belong to other lanes. These are the exact lines to add, and where.

The new module is `ClosedLoopDeployment/stability.py`, with tests in
`ClosedLoopDeployment/tests/test_stability.py` (27 tests, all passing).

---

## Route A, recommended: reuse the answer the biomarkers path already computed

The biomarkers path already runs this test. `Biomarkers.bravo_service._validate_band_core` calls
`analytics.band_stim_stability` and returns the result under the key `"stim"`. Translating that
costs no model fitting at all, so this route adds essentially nothing to the request.

In `ClosedLoopDeployment/adapter.py`, inside `report_for_participant`, **immediately before the
closing `return out`** (currently the line after `out["impedance_status_counts"] = ...`):

```python
    # The "does this band mean the same thing about pain at every current" answer. The biomarkers
    # path already computes it; this only translates it into the four-valued form the report needs,
    # so no model is refitted here. Wrapped because a report that lists every other check is more
    # use to a clinician than a page that will not load.
    try:
        from modules.Biomarkers import bravo_service as _bsvc
        from . import stability as _stab
        _first = (cands[0] or {}) if cands else {}
        _ch, _fc = _first.get("channel"), _first.get("center_hz")
        if _ch is not None and _fc is not None:
            _core = _bsvc._validate_band_core({
                "ParticipantId": getattr(participant, "uid", participant),
                "Channel": _ch, "CenterHz": float(_fc),
                "BandWidthHz": float(_first.get("band_width_hz", 5.0)),
            })
            _raw = (_core.get("stim") or {}) if _core.get("available") else {
                "available": False,
                "reason": (_core.get("reason") or "the biomarkers path returned nothing usable"),
            }
            _finding = _stab.finding_from_stability_result(
                _raw, _ch, float(_fc),
                band_width_hz=float(_first.get("band_width_hz", 5.0)))
            out["band_stability"] = _finding.as_payload()
            out["band_stability_summary"] = _stab.summarise([_finding])
    except Exception as _exc:
        # Say WHY it is missing. A key that is simply absent reads on the page as "not applicable",
        # and this check being unavailable is not the same as it not applying.
        out["band_stability"] = {
            "answer": "not tested", "test_ran": False,
            "reason": f"the stability answer could not be assembled: {_exc!r}",
            "blocking_status": __import__(
                "modules.ClosedLoopDeployment.stability", fromlist=["x"]).BLOCKING_STATUS,
            "answers_possible": list(__import__(
                "modules.ClosedLoopDeployment.stability", fromlist=["x"]).ANSWERS),
        }
```

That is the whole backend change. `out` is already passed through `json_compliant_handler` by
`Server/APIs/DataAnalysis.py::QueryClosedLoopDeployment`, and every value in the payload is plain
data, so no serialiser change is needed.

---

## Route B: run the test from the closed-loop side instead

Use this only if you want the closed-loop page to be able to ask for a band the biomarkers page has
not been asked about. It refits the mixed model, so it is slow and needs R present.

Same insertion point:

```python
    try:
        from . import stability as _stab
        _first = (cands[0] or {}) if cands else {}
        _finding = _stab.assess_band_stability(
            _pooled_detail, _first.get("channel"), float(_first.get("center_hz")),
            stim_series=_stim_series, rate_series=_rate_series,
            band_width_hz=float(_first.get("band_width_hz", 5.0)))
        out["band_stability"] = _finding.as_payload()
        out["band_stability_summary"] = _stab.summarise([_finding])
    except Exception as _exc:
        out["band_stability"] = {"answer": "not tested", "test_ran": False,
                                 "reason": f"stability test failed: {_exc!r}"}
```

`_pooled_detail`, `_stim_series` and `_rate_series` have to be built first; the recipe is the one in
`bravo_service._validate_band_core` — `streaming_psd.build_pooled_detail_from_matrix(...)` for the
first and `availability.stim_series(_load_recordings(uid, CHRONIC_TYPES))` for the second.

**Supply `rate_series` if you take this route.** The biomarkers path currently calls
`band_stim_stability` without it, so the answer it produces cannot see whether the stimulation rate
was changing at the same moments as the current. When that happens the test is partly answering a
question about rate while being reported as an answer about current. Route A inherits that blind
spot; Route B can fix it, and the payload already has the two fields to carry the warning
(`rate_moved_with_current`, `distance_to_nearest_artifact_hz`).

---

## Front end

`Client/src/views/Reports/ClosedLoopSim/BandStabilityPanel.js` is new and complete. No existing
React file was modified. To mount it, add to `ClosedLoopSim/index.js`:

```javascript
import BandStabilityPanel from "./BandStabilityPanel";
```

and, in the panel grid, wherever it should sit relative to the evidence panels:

```javascript
<Grid item xs={12} lg={6}>
  <BandStabilityPanel stability={report?.band_stability} />
</Grid>
```

The panel accepts `stability={null}` and renders an honest empty state, so it can be mounted before
the backend lines above are applied.

---

## The one thing not to change without deciding it on purpose

`stability.py` deliberately exposes **no boolean**. There is no `.stable`, no `.passed`, no `.ok`,
and `as_payload()` contains exactly one true-or-false key (`test_ran`, which says whether the test
ran, not what it concluded). This is enforced by a test. The reason is that the upstream result
still carries the old two-valued `stim_stable` flag, and on this participant's own data that flag
disagrees with the honest answer:

| electrode | band centre | old two-valued `stim_stable` | honest four-valued answer |
|---|---|---|---|
| `ZERO_THREE_RIGHT` | 26.0 Hz | `False` | behaves differently |
| `ONE_THREE_LEFT`   | 17.5 Hz | `True`  | **cannot tell** |

The second row is the whole point. The interaction test did not reject (p = 0.372), so the old flag
reads `True`, which downstream means "stim-stable" and looks like a pass. But the interval on the
largest difference between stimulation states runs from -0.52 to +0.89, which straddles zero and is
wider than the declared margin of 0.69, so the data cannot tell a steady band from a materially
unsteady one. Do not read `stim_stable` on the deployment page. Read `band_stability["answer"]` and
handle all four values.

**Measured on RCS08 on 2026-09-09, at the calibrated grid's own settings: a 5 Hz band, with pain
split into thirds.** The settings are stated because the answer depends on them: the same electrode
and centre gives p = 0.286 with a 1 Hz band and p = 0.032 with a 5 Hz one, so a p-value quoted for
one of these points without its band width beside it is not a reproducible claim.

**This row used to name 12.5 Hz, with p = 0.290 and an interval of -1.23 to +0.22.** That point now
reads "behaves differently" (p = 0.0323, interval -1.238 to -0.104) -- a third value, not the
"cannot tell" this table claimed. The old numbers are kept here as dated history because the reason
they had to be replaced is worth knowing: it is not a code change (Track D's own module, checked out
byte-for-byte and run on today's data, returns 0.0323 to twelve significant figures, both from the
cached spectrum matrix and with that matrix rebuilt), not the pain reports (truncating them back to
2026-09-07 leaves the same 421 rows in 37 groups and the same p), and not new recordings (386
time-domain recordings then and now). What it IS sensitive to is the band width, above.

## Whether this should block a deployment is not decided here

The payload carries `blocking_status` as the phrase
`"not decided - reported for the PI to rule on, blocks nothing today"`, and nothing in the module
adds a blocker or removes a candidate. Making "behaves differently" blocking is defensible and may
well be right, but the blocking rules in this module are device rules traceable to a page of a
Medtronic manual, and this is a statistical finding about one participant. That call is the PI's.
