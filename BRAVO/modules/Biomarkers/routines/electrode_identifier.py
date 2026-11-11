"""The electrode identifier check (the PI, 2026-10-06): what the device's own electrode identifier
recorded, for the Biomarkers page's bottom fold. On no calculation of the platform's.

The electrode identifier records each electrode of one lead against contact 3 of the OTHER lead,
stimulation off, about 20 s per run (white paper UC202012929dEN pp. 3-5; DEVICE_percept_rc.md §3).
So no channel is a within-lead sensing pair, and each mixes both brain sides: these runs are shown
and summarised here, never matched to pain or pooled with a within-lead recording (decision 202).

Device values at face value: the spectrum (µVp per 0.98 Hz bin), the ranking at the frequency the
clinician selected, the selected and peak frequencies and the artefact flag are passed through
unchanged; nothing is computed from a spectrum. The export keeps the PSD of the session's most
recent run only, and some entries carry labels with no values, so many runs have no spectrum.
"""
import statistics

_NUM = {"ZERO": 0, "ONE": 1, "TWO": 2, "THREE": 3}
_RANK = {"HIGHEST_RANK": "highest", "MIDDLE_RANK": "middle", "LOWEST_RANK": "lowest",
         "INSUFFICIENT_SIGNAL_SEPARATION": "insufficient separation", "NOT_AVAILABLE": "not available"}
_IDENTIFIER_SOURCE = "BrainSenseSurveys/ElectrodeIdentifier"


def electrode_label(name, side):
    """ELECTRODE_ZERO_RING / ELECTRODE_ONE_A on a side -> the clinic's number: left 0-3, right 8-11."""
    parts = str(name or "").replace("ELECTRODE_", "").split("_")
    if not parts or parts[0] not in _NUM:
        return str(name)
    n = _NUM[parts[0]] + (8 if str(side).lower().startswith("r") else 0)
    seg = parts[1].lower() if len(parts) > 1 and parts[1] != "RING" else ""
    return f"{n}{seg}"


def _side_of_channel(channel):
    head = str(channel).split("_REFERENCE_")[0]
    return "Left" if head.endswith("_LEFT") else ("Right" if head.endswith("_RIGHT") else None)


def _electrode_of_channel(channel):
    head = str(channel).split("_REFERENCE_")[0]
    return head.rsplit("_", 1)[0]


def _entry_row(e, side):
    values = list(e.get("LFPMagnitudeinMicroVoltPeak") or [])
    return {"electrode": electrode_label(e.get("SensingElectrodes"), side),
            "ranking": _RANK.get(str(e.get("RankingatSelectedFrequency") or ""), "not given"),
            "selected_hz": e.get("SelectedFrequencyInHertz"), "peak_hz": e.get("PeakFrequencyInHertz"),
            "peak_uvrms": e.get("PeakMagnitudeInMicroVoltRMS"),
            "artifact": str(e.get("ArtifactStatus") or "") == "SQC_ARTIFACT_PRESENT",
            "freq": list(e.get("LFPFrequencyinHertz") or []) if values else [], "uvp": values}


def _run_row(t, side, electrodes, entries, run_unknown):
    rows = [_entry_row(e, side) for e in entries]
    other = "right" if side == "Left" else "left"
    ref_entry = next((e for e in entries if e.get("ReferenceElectrode")), None)
    ref_name = ref_entry.get("ReferenceElectrode") if ref_entry else "ELECTRODE_THREE_RING"
    psd = ("with values" if any(r["uvp"] for r in rows)
           else ("entries without values" if rows else "no PSD entry"))
    return {"t": float(t), "side": side, "run_unknown": bool(run_unknown),
            "group": "rings" if all(str(x).endswith("_RING") for x in electrodes) else "segments",
            "reference": f"{electrode_label(ref_name, other)} ({other} lead)",
            "n_channels": len(electrodes), "psd": psd, "electrodes": rows}


def runs(recordings, unknown_spectra):
    """One row per electrode-identifier run, oldest first: the stored runs, then the spectra whose
    run could not be told (decision 443), each flagged and stamped with the session start."""
    out = []
    for r in recordings or []:
        channels = list(r.get("ChannelNames") or [])
        sides = {_side_of_channel(c) for c in channels} - {None}
        entries = [e for e in ((r.get("Descriptor") or {}).get("MedtronicPSD") or []) if isinstance(e, dict)]
        if not sides and entries:
            sides = {str(entries[0].get("Hemisphere") or "")}
        if len(sides) != 1:
            continue
        side = sides.pop()
        electrodes = [_electrode_of_channel(c) for c in channels] or [e.get("SensingElectrodes") for e in entries]
        out.append(_run_row(r.get("StartTime"), side, electrodes, entries, False))
    # The export stores such spectra one electrode per record. Those sharing a session start, side
    # and group are the export's one PSD set (it keeps the session's most recent run only) and form
    # one row; a repeated electrode means two sets, which are never merged.
    sets = {}
    for r in unknown_spectra or []:
        if str(r.get("Source")) != _IDENTIFIER_SOURCE:
            continue
        for e in ((r.get("Descriptor") or {}).get("MedtronicPSD") or []):
            if not isinstance(e, dict):
                continue
            side = "Left" if "Left" in str(e.get("Hemisphere")) else "Right"
            group = "rings" if str(e.get("SensingElectrodes")).endswith("_RING") else "segments"
            sets.setdefault((float(r.get("StartTime")), side, group), []).append(e)
    for (t, side, group), entries in sets.items():
        names = [e.get("SensingElectrodes") for e in entries]
        for chunk in ([entries] if len(set(names)) == len(names) else [[e] for e in entries]):
            out.append(_run_row(t, side, [e.get("SensingElectrodes") for e in chunk], chunk, True))
    return sorted(out, key=lambda x: (x["t"], x["side"], x["group"]))


def summary(rows):
    """Per side and group (never pooled): runs, runs with spectra, how often the device ranked each
    electrode highest among the runs it ranked, its selected frequencies, and artefact flags."""
    out = {}
    for side in ("Left", "Right"):
        for group in ("rings", "segments"):
            rs = [r for r in rows if r["side"] == side and r["group"] == group]
            if not rs:
                continue
            counts, ranked, insufficient, sel, art = {}, 0, 0, [], 0
            for r in rs:
                ranks = [e["ranking"] for e in r["electrodes"]]
                if "insufficient separation" in ranks:
                    insufficient += 1
                if any(k in ("highest", "middle", "lowest") for k in ranks):
                    ranked += 1
                    for e in r["electrodes"]:
                        if e["ranking"] == "highest":
                            counts[e["electrode"]] = counts.get(e["electrode"], 0) + 1
                    hz = [e["selected_hz"] for e in r["electrodes"] if e["selected_hz"]]
                    if hz:
                        sel.append(float(hz[0]))
                art += sum(1 for e in r["electrodes"] if e["uvp"] and e["artifact"])
            top = max(counts.values()) if counts else 0
            out[f"{side} {group}"] = {
                "side": side, "group": group, "n_runs": len(rs),
                "n_with_spectra": sum(1 for r in rs if r["psd"] == "with values"),
                "n_run_unknown": sum(1 for r in rs if r["run_unknown"]),
                "n_ranked": ranked, "n_insufficient_separation": insufficient,
                "highest_counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
                "most_often_highest": sorted(k for k, v in counts.items() if v == top) if counts else [],
                "selected_hz": {"n": len(sel), "median": statistics.median(sel) if sel else None,
                                "min": min(sel) if sel else None, "max": max(sel) if sel else None},
                "n_spectra_with_artifact": art}
    return out
