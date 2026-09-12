"""Read established device facts off the platform, for the rules that need a measurement.

Several rules in ``constraints.py`` cannot be evaluated from the analysis tables alone: they ask
about the state of the hardware. This module supplies those facts from the database and, where a
fact can only come from a person reading the programmer, says so rather than inventing a value.

WHY IMPEDANCE IS READ FROM ``metadata`` AND NOT THROUGH ``Database.loadSourceFile``. Recordings of
type ``MedtronicDeviceImpedance`` carry an EMPTY ``pointer``: there is no ``.bdat`` file for them,
because the payload is small enough to live inline on the row. Calling ``loadSourceFile`` with an
empty pointer trips its path-prefix guard and raises "Malicious Attempt at Accessing Other Data in
the Computer", which reads like a security incident and is nothing of the sort. That exception is
the PREFIX check; the HMAC integrity check raises a different message entirely ("DANGER:
Unauthorized Modification of Data"). Diagnosing this the wrong way round cost a session, so it is
written down here: for this recording type, read ``recording.metadata`` and never call the loader.
"""
from __future__ import annotations

import statistics as _st

#: Lead models whose short-circuit floor is the SenSight value rather than the 1x4 value. The
#: constraint table keys its floor on the string "sensight", so the model number is mapped here
#: rather than at the call site.
_SENSIGHT_MODELS = ("LEAD_B33015", "LEAD_B33005")


def _lead_type(lead_model):
    if not lead_model:
        return None
    return "sensight" if str(lead_model).upper() in _SENSIGHT_MODELS else "1x4"


#: The open-circuit limit D16 uses, duplicated here (rather than imported from ``constraints``)
#: because ``constraints.py`` already imports this module and a circular import would follow.
_OPEN_LIMIT_OHM = 10_000.0


def _measurement_current(metadata):
    """The impedance test's own measurement current, from ``metadata["Amplitude"]``.

    THE PI'S FINDING, 2026-09-12: the device's DEFAULT impedance test steps a low measurement
    current automatically, and at that current a healthy lead can read above the open-circuit
    limit while the same lead reads normal at a fixed, higher current. Measured on RCS08: 351 of
    544 recordings run in the automatic mode read the Left lead's worst pair above 10,000 ohms,
    against 0 of 18 recordings run at a fixed current. This function reads which mode a given
    recording used, so ``impedance_facts`` can prefer a fixed-current reading for D16.

    The raw strings on RCS08's own record are written with no space before the unit --
    "Automatic increasemA", "0.4mA", "1.0mA" -- so this is parsed defensively rather than assuming
    one fixed spelling. Returns ``"automatic_increase"``, a ``float`` number of mA, or ``None``
    when the field is absent or cannot be read.
    """
    raw = (metadata or {}).get("Amplitude")
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower().startswith("automatic"):
        return "automatic_increase"
    if s.lower().endswith("ma"):
        s = s[:-2]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _iso(d):
    """A recording's date as something a report can print.

    Real recordings carry a ``datetime``; the tests in this module use a plain integer, which is
    passed through unchanged rather than forced into a shape it was never given.
    """
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        return d.isoformat()
    # On the live platform ``Recording.date`` is a number of seconds since 1970 (UTC), e.g.
    # 1789140600.0 for 2026-09-11 15:30 UTC; print it as a date rather than as that number.
    try:
        import datetime as _dt
        v = float(d)
        if v > 1e8:
            return _dt.datetime.fromtimestamp(v, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return d


def impedance_facts(recordings):
    """Summarise impedance for D16 from ``MedtronicDeviceImpedance`` recording rows.

    Returns the WORST (highest) bipolar reading per hemisphere rather than a mean, because D16 is a
    fault check: one open contact matters even when the other seven are healthy, and averaging is
    exactly the operation that would hide it. The device's own Status field is carried through
    verbatim, since the manufacturer's judgement of its own hardware outranks our threshold
    arithmetic.

    WHICH RECORD THE PER-HEMISPHERE NUMBERS COME FROM, decided by the PI 2026-09-12 (see
    ``_measurement_current``'s own note for the measurement). ``out["Left"]``, ``out["Right"]`` and
    therefore ``candidate_impedance_ohm`` are read from the NEWEST recording run at a FIXED
    measurement current, when one exists; only when no fixed-current recording is on record do
    they fall back to the newest recording of any kind, which is exactly what this function did
    before this change. ``measurement_current``, ``measured_at`` and ``status_chosen`` describe
    whichever recording was actually used for that choice. ``status_newest``, ``lead_model`` and
    ``lead_type`` still describe the single newest recording of any kind, because they are about
    the device's current state rather than about which reading D16 trusts.
    """
    rows = [r for r in (recordings or []) if getattr(r, "metadata", None)]
    if not rows:
        return {"available": False, "reason": "no impedance recordings on record"}
    rows.sort(key=lambda r: getattr(r, "date", 0) or 0)
    newest_row = rows[-1]
    newest = newest_row.metadata or {}
    newest_current = _measurement_current(newest)

    fixed_rows = [r for r in rows if isinstance(_measurement_current(r.metadata), float)]
    chosen_row = fixed_rows[-1] if fixed_rows else newest_row
    chosen = chosen_row.metadata or {}
    chosen_current = _measurement_current(chosen)

    statuses = {}
    for r in rows:
        s = str((r.metadata or {}).get("Status"))
        statuses[s] = statuses.get(s, 0) + 1

    out = {"available": True, "n_records": len(rows),
           "status_newest": newest.get("Status"),
           "status_counts": statuses,
           "lead_model": (newest.get("Left") or {}).get("LeadModel"),
           "lead_type": _lead_type((newest.get("Left") or {}).get("LeadModel")),
           "measurement_current": chosen_current,
           "measured_at": _iso(getattr(chosen_row, "date", None)),
           "status_chosen": chosen.get("Status")}

    # The historical worst is a DIFFERENT question from the current reading and both matter: a lead
    # whose newest measurement is inside the limits but which has exceeded them before is not the
    # same object as one that never has. Reporting only the newest hid this until the 2026-09-04
    # ingest brought in a newer, better measurement and D16 silently flipped from fail to pass.
    # The "_fixed" figures restrict that same history to recordings run at a fixed measurement
    # current, so a reader can tell whether the record's own worst-ever reading is itself a
    # low-current artefact or a reading a fixed-current test actually confirmed.
    for hemi in ("Left", "Right"):
        hist = [float(x) for r in rows
                for row in (((r.metadata or {}).get(hemi) or {}).get("Bipolar") or [])
                for x in row if x]
        hist_fixed = [float(x) for r in rows
                      if isinstance(_measurement_current(r.metadata), float)
                      for row in (((r.metadata or {}).get(hemi) or {}).get("Bipolar") or [])
                      for x in row if x]
        out.setdefault("history", {})[hemi] = {
            "bipolar_max_ohm_ever": max(hist) if hist else None,
            "n_readings": len(hist),
            "n_above_open_limit": sum(1 for x in hist if x > 10000.0),
            "bipolar_max_ohm_ever_fixed": max(hist_fixed) if hist_fixed else None,
            "n_readings_fixed": len(hist_fixed),
            "n_above_open_limit_fixed": sum(1 for x in hist_fixed if x > 10000.0),
        }

    for hemi in ("Left", "Right"):
        h = chosen.get(hemi) or {}
        bip = [float(x) for row in (h.get("Bipolar") or []) for x in row if x]
        mono = [float(x) for x in (h.get("Monopolar") or []) if x]
        out[hemi] = {
            "bipolar_max_ohm": max(bip) if bip else None,
            "bipolar_min_ohm": min(bip) if bip else None,
            "bipolar_median_ohm": _st.median(bip) if bip else None,
            "monopolar_max_ohm": max(mono) if mono else None,
            "n_bipolar_pairs": len(bip),
        }
        # THE SPURIOUS-FAIL CASE the PI named: the truly newest recording of all ran in the
        # automatic mode and reads above the open-circuit limit, while the fixed-current recording
        # this rule actually trusts reads inside it. Recorded here, per hemisphere, so the ledger
        # can state both numbers rather than only the one D16 acts on.
        if fixed_rows and newest_current == "automatic_increase":
            hn = newest.get(hemi) or {}
            bip_auto = [float(x) for row in (hn.get("Bipolar") or []) for x in row if x]
            auto_worst = max(bip_auto) if bip_auto else None
            chosen_worst = out[hemi]["bipolar_max_ohm"]
            if (auto_worst is not None and auto_worst > _OPEN_LIMIT_OHM
                    and chosen_worst is not None and chosen_worst <= _OPEN_LIMIT_OHM):
                out[hemi]["automatic_newest_ohm"] = auto_worst
                out[hemi]["automatic_newest_date"] = _iso(getattr(newest_row, "date", None))
    return out


def candidate_impedance_ohm(facts, hemisphere):
    """The single number D16's predicate compares against its short and open limits.

    The WORST bipolar reading on the sensing hemisphere. A sensing channel is a bipolar pair, so a
    bipolar reading is the right quantity; taking the worst on the hemisphere is deliberately
    conservative, because the matrix index to contact-label mapping for a segmented SenSight lead is
    not one-to-one and picking the wrong cell would silently report a healthy pair in place of a
    faulty one.
    """
    if not (facts or {}).get("available"):
        return None
    return ((facts.get(hemisphere) or {}).get("bipolar_max_ohm"))


# ---------------------------------------------------------------------------------------------
# FACTS THAT CAN ONLY COME FROM A PERSON READING THE PROGRAMMER
# ---------------------------------------------------------------------------------------------
#: Values the investigator supplied directly, with the date and the fact that they were STATED
#: rather than measured from the record. This block is a stopgap and should be read as one: these
#: belong in a per-participant database row with an audit trail, not in source. They are here, with
#: provenance on every line, because the alternative was leaving eleven device rules unevaluable —
#: and an unevaluable rule blocks, so the whole verdict was stuck behind values that take two
#: minutes to read off a programmer.
#:
#: The rule for adding to this block: a value goes here ONLY if a person read it off the device or
#: stated it as a clinical decision. Anything derivable from the record must be derived, because a
#: stated value cannot be re-checked when the record changes. Two candidate values were REFUSED
#: entry on exactly that basis — the LFP capture amplitude (D09), because the surveys measure it and
#: the stated estimate of 2 uVp would have passed a gate the measured 0.27 uVp median fails, and
#: the impedance (D16), because 548 recordings carry it.
PI_STATED_FACTS = {
    "2e3c75c00d7f4f37b53a048d195f11da": {          # RCS08
        #: D32. Stated 2026-09-05 in answer to a direct question: no pocket adaptor, each lead
        #: connects to the Percept RC directly. A pocket adaptor is a short connector body used in
        #: the generator pocket to mate a lead or extension whose connector does not fit the
        #: generator, and A610 pp. 34-35 states that BrainSense cannot be configured in a
        #: hemisphere containing one. This CANNOT be derived: no field in any of the 1,154 session
        #: reports records accessory hardware, because the implant knows its leads and not what is
        #: spliced in front of them. It is a fact from the operative record.
        "has_pocket_adaptor": False,
        #: D29. Stated 2026-09-05: "there are no vertically aligned segments that are stimulated
        #: anymore. It's all ring stimulation." A610 p. 39 requires vertically aligned segments to
        #: share amplitude and electrode polarity when BrainSense is configured, and that condition
        #: only arises when aligned segments are DIRECTIONALLY STEERED, meaning driven at different
        #: current fractions. Activating 1a, 1b and 1c together at equal fraction is ring
        #: stimulation implemented on a segmented level, and the rule does not bear on it.
        #:
        #: MEASURED, and not exactly zero, which is why the number is written down rather than
        #: the ruling. Across all 1,154 session reports 98.50% of segmented levels are ring-mode
        #: (13,918 of 14,130): 13,550 have all three segments at one identical current fraction and
        #: 368 have a single segment active. The remaining 212 levels (1.50%) DO carry unequal
        #: fractions, for example -21 with -9. The PI's word was "anymore", so historical steering
        #: is consistent with the statement, but this flag is set to False on a 98.50% measurement
        #: plus a clinical ruling, not on a clean zero.
        #:
        #: It is nonetheless the right value for THIS rule, for a reason independent of the
        #: percentage: those 212 are steered WITHIN a level -- two segments of the same level at
        #: different fractions -- and p. 39 compares segments ACROSS levels at the same angular
        #: position. On that comparison the amplitude mismatch count is ZERO across all 17,102
        #: vertically aligned pairs, so the condition the rule guards against does not occur in
        #: this record at all.
        #:
        #: Recorded because my own check misread this. It flagged 600 of those 17,102 pairs as
        #: mismatched, but every one was a ring-to-ring bipolar montage (level 1 at +21/64 as the
        #: anode ring, level 2 at -21/64 as the cathode ring) rather than a steered pair. The
        #: magnitudes matched in every single pair; only the sign differed, which is what makes a
        #: bipolar configuration bipolar. Seeing segment NAMES in the contact list is not evidence
        #: that steering is in use.
        "segmental_steering_in_use": False,
        #: D31. Stated 2026-09-05: "we're gonna use 55 Hertz. That's it." This is the deployment
        #: rate decision, not a device limit. It is recorded here so a candidate builder uses the
        #: chosen rate rather than carrying forward the 165 Hz configuration that earlier screens
        #: were built around.
        "deployment_rate_hz": 55.0,
        #: D04. Stated 2026-09-04: a single implanted neurostimulator.
        "n_neurostimulators": 1,
        #: D13. Stated 2026-09-04: the user-configurable high-pass is set to 1 Hz, the lower of the
        #: two selectable values. This matters for a low-centre band: a 10 Hz high-pass would
        #: attenuate the alpha peak that is the only part of this device's spectrum reaching the
        #: capture floor.
        "highpass_hz": 1.0,
        #: D15. Stated 2026-09-04 and CONFIRMED against the record rather than taken on trust:
        #: ONE_THREE_LEFT appears as a configured sensing channel in the session reports.
        "channel_is_brainsense_setup_channel": True,
        #: D34. Stated 2026-09-04, after an explicit correction: 2.5 mA on the LEFT and 2.0 mA on
        #: the RIGHT. The first statement had the sides the other way round, so the assignment is
        #: recorded per side rather than as a single number. These are INTENDED values: the device
        #: record's SuspendAmplitude fields read 0.0, 1.3 and 1.5 mA, none of them 2.5 or 2.0, so
        #: nothing here has been programmed yet.
        "paused_amplitude_mA_by_hemisphere": {"Left": 2.5, "Right": 2.0},
    },
}


#: D31. WHAT THE DEVICE HAS ACTUALLY ACCEPTED, per hemisphere, as (rate_hz, pulse_width_us).
#:
#: Measured 2026-09-05 by walking all 1,154 session reports and collecting every group carrying a
#: ``SensingChannel``. This exists because D31 was written to compare a candidate against the
#: BrainSense parameter envelope, and that envelope is NOT PUBLISHED: the A610 guide states only
#: that the maximum pulse width and maximum rate are lower and the minimum rate higher than for a
#: group without BrainSense, without giving any of the three numbers, and a search of the entire
#: JSON corpus found no field carrying them either. The only path in 1,154 files combining a
#: rate/pulse-width/frequency name with a limit word is ``IndefiniteStreaming[].SampleRateInHz``,
#: which is the sensing sample rate and not a stimulation limit.
#:
#: So the rule stops asking for a number it will never get and asks an answerable question instead:
#: has this exact rate and pulse width been programmed in a BrainSense group on this hemisphere?
#: A demonstrated configuration is stronger evidence than a limit comparison, because the device
#: itself accepted it.
#:
#: Two asymmetries in this table matter and would be hidden by pooling the hemispheres. 55 Hz with
#: 60 us appears 1,274 times on the LEFT and never on the right; 165 Hz with 60 us appears 152
#: times on the LEFT and never on the right, where 165 Hz has only run at 80 and 160 us. The
#: observed minimum rate in a sensing group is 55 Hz on both sides against 10 Hz in non-sensing
#: groups, which is consistent with the guide's claim that the BrainSense minimum is higher, and
#: bounds it at 55 Hz or below without revealing its value.
BRAINSENSE_PROGRAMMED_PAIRS = {
    "Left": {
        (55.0, 60.0): 1274, (55.0, 100.0): 280, (55.0, 140.0): 4, (55.0, 180.0): 72,
        (110.0, 60.0): 104, (110.0, 100.0): 692, (110.0, 180.0): 14,
        (125.0, 60.0): 30,
        (145.0, 60.0): 12, (145.0, 120.0): 92, (145.0, 140.0): 164, (145.0, 180.0): 14,
        (165.0, 60.0): 152, (165.0, 140.0): 76,
    },
    "Right": {
        (55.0, 150.0): 160, (55.0, 160.0): 3146, (55.0, 180.0): 36,
        (110.0, 60.0): 304, (110.0, 100.0): 438, (110.0, 180.0): 258,
        (125.0, 60.0): 80,
        (145.0, 60.0): 88, (145.0, 140.0): 260, (145.0, 160.0): 80, (145.0, 180.0): 26,
        (165.0, 80.0): 152, (165.0, 160.0): 322,
    },
}

#: Provenance for the table above, carried onto the report so a reader can tell a measurement from
#: an assertion and can see how stale it is.
BRAINSENSE_PAIRS_PROVENANCE = (
    "measured 2026-09-05 from all 1,154 RCS08 session reports; counts are group records carrying "
    "a SensingChannel, not distinct programming events"
)


def brainsense_pair_programmed(rate_hz, pulse_width_us, hemisphere):
    """Has this exact (rate, pulse width) been programmed in a BrainSense group on this side?

    Returns True when the pair appears in the measured table, False when the hemisphere is known
    and the pair is absent from it, and None when any input is missing or the hemisphere is not
    one this device has. The False case is deliberately NOT a device prohibition: absence means the
    combination has never been demonstrated here, which is a weaker statement than being
    forbidden, and the caller must present it that way.
    """
    if hemisphere not in BRAINSENSE_PROGRAMMED_PAIRS:
        return None
    if rate_hz is None or pulse_width_us is None:
        return None
    try:
        key = (float(rate_hz), float(pulse_width_us))
    except (TypeError, ValueError):
        return None
    return key in BRAINSENSE_PROGRAMMED_PAIRS[hemisphere]


def facts_for_participant(participant_uid, impedance_recordings=None, *,
                          hemisphere=None, channel=None):
    """Assemble every device fact this module can establish for one participant.

    Measured values take precedence over stated ones wherever both exist, and the returned dict
    records which is which under ``_provenance`` so a reader can tell a reading from an assertion.
    """
    stated = dict(PI_STATED_FACTS.get(str(participant_uid), {}))
    out, prov = {}, {}

    paused = stated.pop("paused_amplitude_mA_by_hemisphere", None)
    if paused and hemisphere in (paused or {}):
        out["paused_amplitude_mA"] = paused[hemisphere]
        prov["paused_amplitude_mA"] = f"stated by PI 2026-09-04 for the {hemisphere} hemisphere"
    for k, v in stated.items():
        out[k] = v
        prov[k] = "stated by PI 2026-09-04"

    imp = impedance_facts(impedance_recordings or [])
    if imp.get("available"):
        ohm = candidate_impedance_ohm(imp, hemisphere) if hemisphere else None
        if ohm is not None:
            out["impedance_ohms"] = ohm
            # Be exact about what this number IS. It is the worst bipolar pair WITHIN the record
            # D16 actually trusts (the newest FIXED-current test when one exists, decision
            # 2026-09-12; otherwise the newest test of any kind, which is the whole record here
            # before that decision) — and the difference is not academic: on 2026-09-04 an ingest
            # brought in a newer, better measurement and D16 flipped from fail to pass with no code
            # change, while 1265 of 15540 historical left-lead readings remain above the
            # open-circuit limit. The old wording said "across N recordings", which would have let
            # a reader take a currently-sound lead for a never-faulty one.
            _hist = ((imp.get("history") or {}).get(hemisphere) or {})
            _worst_ever_txt = (
                f"worst EVER {_hist.get('bipolar_max_ohm_ever')} ohm with "
                f"{_hist.get('n_above_open_limit')} of {_hist.get('n_readings')} readings above "
                f"the 10000 ohm open limit")
            _cur = imp.get("measurement_current")
            out["impedance_measurement_current"] = _cur
            out["impedance_measured_at"] = imp.get("measured_at")
            if isinstance(_cur, float):
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the newest FIXED-current impedance test "
                    f"({_cur:g} mA, {imp.get('measured_at')}, device status "
                    f"{imp.get('status_chosen')}) on the {hemisphere} lead; {_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    f"measured: {_cur:g} mA, the Amplitude field of the impedance test D16 uses "
                    f"for the {hemisphere} lead")
                _hemi_block = imp.get(hemisphere) or {}
                _auto_ohm = _hemi_block.get("automatic_newest_ohm")
                _auto_date = _hemi_block.get("automatic_newest_date")
                if _auto_ohm is not None:
                    out["impedance_ohms_automatic_newest"] = _auto_ohm
                    out["impedance_automatic_measured_at"] = _auto_date
                    prov["impedance_ohms"] += (
                        f". The newest impedance test of all ({_auto_date}) used the automatic "
                        f"low-current mode and read {_auto_ohm:g} ohm, which the PI has ruled a "
                        f"spurious fail at that measurement current (2026-09-12), not a real open "
                        f"circuit")
            elif _cur == "automatic_increase":
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the NEWEST impedance test on the "
                    f"{hemisphere} lead ({imp.get('measured_at')}, device status "
                    f"{imp.get('status_chosen')}), which used the device's automatic low-current "
                    f"mode; no fixed-current impedance test is on record, and one would settle "
                    f"whether this reading is a spurious fail at low measurement current "
                    f"(PI decision 2026-09-12); {_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    "measured: the device's automatic low-current mode, the only impedance test "
                    f"on record for the {hemisphere} lead")
            else:
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the NEWEST of {imp['n_records']} impedance "
                    f"recordings on the {hemisphere} lead (status {imp.get('status_newest')}); "
                    f"{_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    "measured: no measurement current was recorded on the impedance test used")
            prov["impedance_measured_at"] = (
                f"measured: date of the impedance test D16 uses for the {hemisphere} lead")
        out["impedance_tested"] = True
        prov["impedance_tested"] = f"measured: {imp['n_records']} impedance recordings on record"
        if imp.get("lead_type"):
            out["lead_type"] = imp["lead_type"]
            prov["lead_type"] = f"measured: LeadModel {imp.get('lead_model')}"
        out["_impedance_status"] = imp.get("status_newest")
        out["_impedance_status_counts"] = imp.get("status_counts")
    # Facts from the raw session reports: capture amplitudes, adaptive limits, the device's own
    # artefact verdict, cycling, and the per-bin LFP spectrum D09 consumes.
    srf, srf_prov = session_report_facts_for(participant_uid, channel=channel,
                                             hemisphere=hemisphere)
    for k, v in srf.items():
        if v is not None and out.get(k) is None:
            out[k] = v
            prov[k] = srf_prov.get(k, "measured: session reports")

    out["_provenance"] = prov
    return out


# ---------------------------------------------------------------------------------------------
# FACTS FROM THE SESSION REPORTS
# ---------------------------------------------------------------------------------------------
#: Fraction of a channel's surveys that must flag an artefact before D17 treats the channel as
#: contaminated. DECLARED BY THIS MODULE, not published by the manufacturer, whose guidance is
#: qualitative. Set at one half — the artefact must be the channel's prevailing state, not an
#: occasional observation — because D17's predicate is categorical and a rule that refuses a
#: configuration on four adverse surveys out of two hundred is answering a different question from
#: the one it asks. The rate itself is always reported regardless of this threshold, so softening
#: the gate does not hide the observation.
ARTIFACT_FLAG_RATE_LIMIT = 0.5

#: Artefact statuses that do NOT count against D17. PI decision, 2026-09-04: "ignore the impedance
#: failures, they should count normally."
#:
#: The reasoning, so a later reader does not undo it as an oversight. D17 asks whether the device
#: detected a SIGNAL artefact on the sensing channel — cardiac, motion or atypical morphology — any
#: of which corrupts the band-power estimate the control loop would read. ``IMPEDANCE_FAILURE`` is
#: not that. It reports that the electrode's impedance measurement failed or fell outside range,
#: which is a statement about the hardware and is already governed by D16, where it is evaluated
#: against the manufacturer's published short and open limits. Counting it here as well penalises
#: one hardware fact twice through two independent rules, and the second penalty carries no
#: additional information: on this participant the same four surveys drive both. A survey whose
#: only adverse finding is an impedance failure is therefore treated as a normal survey for D17,
#: and the impedance question is answered where it belongs.
#:
#: The status is still COUNTED AND REPORTED in ``artifact_flag_counts``, so nothing is hidden — it
#: simply does not enter the numerator of the artefact rate. D16 continues to carry the lead's full
#: impedance history, including the 1265 of 15540 left-lead readings above the open-circuit limit.
D17_NON_ARTEFACT_STATUSES = ("ARTIFACT_NOT_PRESENT", "IMPEDANCE_FAILURE")


#: Per-participant summary produced by ``session_report_facts.scan_folder``. Committed next to the
#: module because the scan takes ~4 minutes over 8.5 GB of reports and its result is a 34 KB
#: summary; re-scanning per request is not an option and re-scanning per session is wasteful. The
#: file records ``n_files`` so a reader can tell which pass produced it.
_SUMMARY_FILES = {"2e3c75c00d7f4f37b53a048d195f11da": "_facts_RCS08.json"}


def _load_summary(participant_uid):
    import json as _json
    import os as _os
    name = _SUMMARY_FILES.get(str(participant_uid))
    if not name:
        return {}
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), name)
    try:
        with open(path) as fh:
            return _json.load(fh)
    except Exception:
        return {}


def session_report_facts_for(participant_uid, *, channel=None, hemisphere=None):
    """Facts for the six rules the platform decoder does not keep in queryable form.

    Every value here comes from the raw session reports rather than a person's recollection, and the
    DISTRIBUTION is carried alongside the newest value because for several of these rules the
    distribution is the finding — D27 is violated by 90% of the right-hemisphere capture records
    while the most recent capture is compliant, and reporting only one of those would mislead.
    """
    from . import session_report_facts as _srf
    S = _load_summary(participant_uid)
    if not S:
        return {}, {}
    out, prov = {}, {}
    n = S.get("n_files")
    tag = f"measured: session reports, {n} files"

    # D28 — adaptive limits and whether adaptive has ever run
    cap = (S.get("capture_newest") or {}).get(hemisphere or "") or {}
    if cap.get("lower_mA") is not None:
        out["capture_amp_low_mA"] = float(cap["lower_mA"])
        prov["capture_amp_low_mA"] = tag + " (newest capture)"
    if cap.get("upper_mA") is not None:
        out["capture_amp_high_mA"] = float(cap["upper_mA"])
        prov["capture_amp_high_mA"] = tag + " (newest capture)"
        # D28: the adaptive amplitude limits INHERIT the capture amplitudes (A610 p. 41).
        out["adaptive_min_mA"] = float(cap["lower_mA"]) if cap.get("lower_mA") is not None else None
        out["adaptive_max_mA"] = float(cap["upper_mA"])
        prov["adaptive_max_mA"] = tag + " (inherited from capture per D28)"
    if cap.get("pw_us") is not None:
        out["capture_pulse_width_us"] = float(cap["pw_us"])
        prov["capture_pulse_width_us"] = tag + " (newest capture)"

    # D17 — the device's own artefact verdict for this channel
    # D17 AND EVER-PRESENCE: a bug of mine, fixed 2026-09-04. The device raises an artefact flag
    # PER SURVEY, and this code used to flatten the per-channel counts into a presence list — so a
    # channel with 188 surveys reading ARTIFACT_NOT_PRESENT and 4 reading IMPEDANCE_FAILURE handed
    # D17 the list ['IMPEDANCE_FAILURE', 'SQC_ARTIFACT_PRESENT'] and the predicate, which tests
    # `len(flags) == 0`, refused the configuration outright on a 1.7% flag rate accumulated over
    # every survey ever recorded. That is not what the rule asks. The rule asks whether an artefact
    # is flagged on the channel we are about to use, and a flag seen four times in two hundred
    # surveys is a quality observation to report, not a categorical bar.
    #
    # The fix reports the RATE and applies the flag only when it is the prevailing state of the
    # channel. The threshold below is OURS, not the manufacturer's, and it is stated here so it can
    # be argued with: a channel whose surveys flag an artefact more often than not is treated as
    # contaminated, and anything less is reported as a rate. The device's own guidance is
    # qualitative ("using a configuration with an artefact detected may interfere"), so no published
    # rate exists to defer to.
    art = S.get("artifact_status") or {}
    key = _match_survey_channel(art, channel, hemisphere)
    if key:
        counts = {k: v for k, v in (art.get(key) or {}).items() if k}
        total = sum(counts.values())
        adverse = {k: v for k, v in counts.items()
                   if k not in D17_NON_ARTEFACT_STATUSES}
        n_adverse = sum(adverse.values())
        rate = (n_adverse / total) if total else None
        out["artifact_flag_rate"] = rate
        out["artifact_flag_counts"] = counts
        # The flag list the predicate consumes now carries only the PREVAILING state.
        out["artifact_flags"] = (sorted(adverse) if (rate is not None and rate > ARTIFACT_FLAG_RATE_LIMIT)
                                 else [])
        out["artifact_excluded_counts"] = {k: v for k, v in counts.items()
                                           if k in D17_NON_ARTEFACT_STATUSES
                                           and k != "ARTIFACT_NOT_PRESENT"}
        prov["artifact_flags"] = (
            tag + f" (channel {key}: {n_adverse} of {total} surveys flag a SIGNAL artefact, "
            f"{100 * rate:.1f}%, against a {100 * ARTIFACT_FLAG_RATE_LIMIT:.0f}% limit declared by "
            f"this module. IMPEDANCE_FAILURE is excluded from the numerator by PI decision because "
            f"D16 governs impedance; counts {counts})")
        prov["artifact_flag_rate"] = prov["artifact_flags"]

    # D32 — cycling is the only one of the five feature exclusions the reports carry
    # D32 reads the SENSING groups only; see session_report_facts for why the earlier
    # device-wide count was answering a different question.
    # D32's five feature exclusions, read from the NEWEST ACTIVE SENSING GROUP — the configuration
    # a clinician would actually program — with the device-wide history reported alongside.
    cyc = S.get("cycling_by_group_kind") or {}
    d32 = S.get("d32_newest_active_sensing_group") or {}
    for k in ("cycling_in_group", "multiple_rates_in_group", "interleaving_in_group",
              "patient_limits_configured", "has_pocket_adaptor"):
        if d32.get(k) is not None:
            out[k] = d32[k]
            prov[k] = tag + " (newest ACTIVE group with sensing configured)"
    if "cycling_in_group" in out:
        prov["cycling_in_group"] = (
            tag + f" (GroupSettings.Cycling.Enabled in the newest ACTIVE sensing group = "
            f"{out['cycling_in_group']}; device-wide history, keyed sensing/active/enabled: {cyc})")
    if d32:
        prov["_d32_group_shape"] = (
            f"{d32.get('n_programs')} program(s), rates {d32.get('rates_seen')}, "
            f"pulse widths {d32.get('pulse_widths_seen')}")

    # D09 — the per-bin spectrum, which is the form the rule now consumes
    bins = _srf.candidate_lfp_bins(S, channel, hemisphere) if channel else []
    if bins:
        out["lfp_bins_uvp"] = bins
        prov["lfp_bins_uvp"] = tag + f" ({len(bins)} survey bins, median per bin)"
    return out, prov


def _match_survey_channel(mapping, channel, hemisphere):
    """Reconcile a candidate's channel name with the survey's electrode-pair spelling.

    A candidate says ``ONE_THREE_LEFT``; the survey says ``ONE_AND_THREE_Left``. Returning None
    when no match is found is deliberate — a rule that receives no flags reports "not determinable"
    rather than "no artefact", and inventing the latter is how a contaminated channel would pass.
    """
    if not channel:
        return None
    want = str(channel).upper().replace("_LEFT", "").replace("_RIGHT", "").replace("_", "")
    for key in mapping:
        pair, _, hemi = str(key).rpartition("_")
        if hemisphere and hemi.lower() != str(hemisphere).lower():
            continue
        if pair.upper().replace("_AND_", "").replace("_", "") == want:
            return key
    return None


# ---------------------------------------------------------------------------------------------
# THE DEVICE'S ACTIVE SENSING GROUP, READ LIVE FROM THE NEWEST SESSION REPORT (D30)
# ---------------------------------------------------------------------------------------------
# WHY THIS IS NOT READ FROM ``_facts_RCS08.json``. That committed summary was scanned once and is
# stale on exactly this point: it says the newest active sensing group runs at 110 Hz, and the
# device's newest session report (SessionDate 2026-09-11T15:30:00Z) says GROUP_D at 55 Hz. D30
# asks whether the candidate's rate is the one already frozen in the device, so it has to read
# the device as it is today, not as a scan of it was on 2026-09-05. The report is decrypted from
# the file the ingest stored (``DataCurator.loadCacheFile``), the same route
# ``StimOptimizer.adapter`` already takes for the therapy history.
#
# WHY THERE IS A MEMO, AND WHAT IT IS KEYED ON. Decrypting and parsing an 8-15 MB session report
# costs real time on every page load, and the answer changes only when a new report is ingested.
# The memo is keyed on the participant AND the newest report's own file identity (its uid and its
# stored hash), never on the participant alone -- decision 130's lesson: the daily noon ingest adds
# a file, and a participant-keyed memo would keep serving yesterday's group until a worker happened
# to restart. A new file is a new key and therefore a miss; a repeat request costs one database
# query for the file list and nothing else.
_ACTIVE_GROUP_MEMO = {}
_ACTIVE_GROUP_MEMO_MAX = 32


def active_sensing_group_from_report(d):
    """The device's newest ACTIVE group with sensing configured, from one decoded session report.

    Pure: takes the report as a dict and returns a dict, so it is testable with no Django. Reads
    ``Groups.Final`` -- the groups as they stood at the END of the session, which is what the device
    left the clinic running -- and takes the first group that is both ``ActiveGroup`` and carries at
    least one ``SensingChannel``. An active group WITHOUT sensing is not it (D30 is about the rate
    BrainSense froze), and an inactive group with sensing is not it either (a group nobody is
    running freezes nothing a clinician is about to program against).

    Returns ``{}`` when the report has no such group, so the caller supplies nothing and D30 stays
    not determinable rather than being handed a fabricated rate.
    """
    if not isinstance(d, dict):
        return {}
    groups = (d.get("Groups") or {}).get("Final") or []
    for g in groups:
        if not isinstance(g, dict) or not g.get("ActiveGroup"):
            continue
        ps = g.get("ProgramSettings") or {}
        sens = ps.get("SensingChannel") or []
        if not sens:
            continue
        rate = ps.get("RateInHertz")
        try:
            rate = float(rate) if rate is not None else None
        except (TypeError, ValueError):
            rate = None
        out = {
            # The export spells the group as an enum ("GroupIdDef.GROUP_D"); keep the part a
            # clinician would say, "GROUP_D".
            "active_sensing_group": str(g.get("GroupId")).split(".")[-1] if g.get("GroupId") is not None else None,
            "active_sensing_group_rate_hz": rate,
            "active_sensing_group_pulse_widths_us": [c.get("PulseWidthInMicroSecond")
                                                     for c in sens if isinstance(c, dict)],
            "active_sensing_group_adaptive_status": [c.get("AdaptiveTherapyStatus")
                                                     for c in sens if isinstance(c, dict)],
            "session_report_date": d.get("SessionDate"),
        }
        return out
    return {}


def _memoised_active_group_facts(key, build):
    """Serve ``build()``'s answer from the memo under ``key``; a new key is a miss.

    Split out from ``active_sensing_group_facts`` so the miss-on-new-file rule can be tested with
    no database: the key is the file identity, and the test changes it.
    """
    hit = _ACTIVE_GROUP_MEMO.get(key)
    if hit is not None:
        return dict(hit)
    facts = dict(build() or {})
    if len(_ACTIVE_GROUP_MEMO) >= _ACTIVE_GROUP_MEMO_MAX:
        _ACTIVE_GROUP_MEMO.pop(next(iter(_ACTIVE_GROUP_MEMO)))
    _ACTIVE_GROUP_MEMO[key] = dict(facts)
    return facts


def active_sensing_group_facts(participant):
    """The device's newest active sensing group for one participant, read live from the newest
    ingested session report; ``{}`` when there is no session report or no active sensing group.

    The Django imports live inside the function because this module is imported by tests that
    have no Django. ``participant`` may be a Participant row or its uid.
    """
    import json as _json
    from Server import models as _m
    from modules import DataCurator as _DC

    p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
    if p is None:
        return {}
    sfs = [s for s in _m.SourceFile.find_all(owner=p) if "Session" in (s.name or "")]
    if not sfs:
        return {}
    newest = max(sfs, key=lambda s: s.date or 0)
    key = (str(p.uid), str(newest.uid), str(newest.hashed or ""))

    def _build():
        raw = _DC.loadCacheFile(newest)
        d = _json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        return active_sensing_group_from_report(d)

    return _memoised_active_group_facts(key, _build)
