"""Synthetic independent contract checks; no database, credentials or network."""
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

spec = importlib.util.spec_from_file_location("aditya_presentation_under_test", Path(__file__).parents[1] / "AdityaPresentation.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.mark.parametrize("value,expected", [(None,None),(True,None),("bad",None),({},None),(float("nan"),None),(float("inf"),None),(0,0),("2.5",2.5)])
def test_finite(value, expected):
    assert p.finite(value) == expected


def test_private_context_is_explicit_and_participant_scoped(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAVO_ADITYA_PRESENTATION_METADATA", raising=False)
    assert p.read_context("a") == {}
    path = tmp_path / "context.json"
    monkeypatch.setenv("BRAVO_ADITYA_PRESENTATION_METADATA", str(path))
    path.write_text(json.dumps({"schema_version": 2}))
    with pytest.raises(ValueError):
        p.read_context("a")
    path.write_text(json.dumps({"schema_version":1, "participants":{"a":{"reviewed":True,"revision":"v1","phases":[],"secret":"never"},"b":{"reviewed":False}}}))
    assert p.read_context("a") == {"revision":"v1","phases":[]}
    assert p.read_context("b") == p.read_context("c") == {}


def test_pain_preserves_canonical_scale_and_separates_sheet():
    canonical = {"metrics":[{"key":"mpq_sum","label":"MPQ Sum","range":[0,72],"points":[
        {"t_epoch":100,"v":62},{"t_epoch":101,"v":63,"sheet":True},
        {"t_epoch":None,"v":10},{"t_epoch":103,"v":float("nan")} ]},
        {"key":"left_leg_vas","label":"Left Leg VAS","range":[0,100],"points":[{"t_epoch":200,"v":50,"record":"report-4"}]}]}
    result = p.pain_timeline(canonical)
    assert result["metrics"][0] == {"key":"mpq_sum","label":"MPQ Sum","range":[0,72],"points":[{"time":100.,"value":62.,"record":None,"phase":None,"source":"REDCap"}]}
    assert result["metrics"][1]["key"] == "left_leg_vas_intensity"
    assert result["visits"]["metrics"]["mpq_sum"][0]["source"] == "clinic-sheet"
    assert result["provenance"]["record_identity_available"] is False
    assert result["comparisons"]["stimulation"]["available"] is False
    assert result["phases"] == []


def test_pain_empty_and_reviewed_context():
    assert not p.pain_timeline({})["visits"]["available"]
    context = {"revision":"r", "phases":[{"key":"stage"}],"home_transitions":[{"id":"known"}],"comparisons":{"medications":{"available":True}}}
    result = p.pain_timeline({}, context, [{"id":"observation"}])
    assert result["stimulation"]["home_transitions"] == [{"id":"known"}]
    assert result["stimulation"]["settings_observations"] == [{"id":"observation"}]
    assert result["comparisons"]["medications"]["available"]
    result["phases"].append({})
    assert len(context["phases"]) == 1


def test_settings_are_observations_and_units_preserved():
    hist = {"TherapyConfiguration":[{"History":[{"Date":None},{"Date":200,"Id":"t1","SourceId":"source-id", "GroupName":"A","StimulationType":"Adaptive",
        "StimulationSettings":[{"Electrode":{"Target":"Left VPL"},"Frequency":130,"Amplitude":2.5,"AmplitudeUnit":"mA","Pulsewidth":60,"PulsewidthUnit":"µs","Contact":["1","2"],"ReturnContact":["CAN"],"Cycling":0.5,"CyclingPeriod":10},
            {"Electrode":{"Target":"Right dACC"},"Frequency":None}, {"Electrode":{"Target":"Unknown"}}]},
        {"Date":100}]}]}
    rows = p.therapy_observations(hist)
    assert [r["time"] for r in rows] == [100,200]
    assert rows[0]["mode"] == "unknown"
    assert rows[0]["source_ids"] == []
    row = rows[1]
    assert row["kind"] == "settings_observation"
    assert {item["label"]:item["value"] for item in row["settings"]["left"]}["Amplitude"] == "2.5 mA"
    assert not any(item["label"] == "Cycling" for item in row["settings"]["left"])
    assert any(item["label"] == "Cycling" for item in row["settings"]["group"])


def sleep(day="2026-01-01", start=1000, end=4600, duration=3600, **kw):
    return {"Metadata":{"DayLabel":day},"Descriptor":{"BedtimeStart":start,"BedtimeEnd":end,"TotalSleepDuration":duration}, **kw}


def metric(result, key):
    return next(m for m in result["metrics"] if m["key"] == key)


def test_oura_original_day_daily_conflicts_and_missing():
    row = lambda day, steps: {"Metadata":{"DayLabel":day},"Descriptor":{"Steps":steps}}
    data = {"DailyActivity":[row("2026-01-01",1234),row("2026-01-01",1234),row("2026-01-02",2),row("2026-01-02",3),row("invalid",10),row("2026-01-03",None),row("2026-01-04",-1)],
            "DailyReadiness":[{"Metadata":{"DayLabel":"2026-01-01","Score":75}}]}
    result = p.oura_timeline(data)
    assert metric(result,"steps")["points"] == [{"day":"2026-01-01","value":1234},{"day":"2026-01-02","value":None},{"day":"2026-01-03","value":None},{"day":"2026-01-04","value":None}]
    assert metric(result,"readiness")["points"][0]["value"] == 75
    assert result["defaults"] == ["steps"]
    assert result["provenance"]["qc_versions"] == []


def test_oura_sleep_dedup_naps_overlap_and_invalid():
    data = {"Sleep":[sleep(),sleep(),sleep(start=5000,end=6800,duration=1800),
            sleep(day="2026-01-02"),sleep(day="2026-01-02",start=2000,end=5600),
            sleep(day="2026-01-03",duration=3601),sleep(day="2026-01-04",start=None),
            sleep(day="bad"),sleep(day="2026-01-05"),sleep(day="2026-01-05",duration=3500)]}
    points = metric(p.oura_timeline(data),"sleep_total")["points"]
    assert points[0] == {"day":"2026-01-01","value":1.5}
    assert all(row["value"] is None for row in points[1:])


def test_oura_samples_mask_gap_conflict_and_original_day():
    row = sleep(StartTime=1000,SamplingRate=1/300,Data=[[50,20],[-1,30],[60,40],[70]],Missing=[[0,0],[0,1],[1,0]])
    conflict = sleep(StartTime=1000,SamplingRate=1/300,Data=[[51,20]],Missing=[[0,0]])
    invalid = sleep(StartTime=None,SamplingRate=0)
    result = p.oura_timeline({"Sleep":[row,conflict,invalid]})
    assert metric(result,"sleep_heart_rate")["points"] == [
        {"day":"2026-01-01","time":1000,"value":None},{"day":"2026-01-01","time":1300,"value":None},
        {"day":"2026-01-01","time":1600,"value":None},{"day":"2026-01-01","time":1900,"value":None}]
    assert metric(result,"sleep_hrv")["points"][2]["value"] == 40


def test_windows_dst_and_inclusive_custom():
    rows = p.date_windows({"window":"custom","start_date":"2026-03-08","end_date":"2026-03-08"}, {})
    assert rows[0]["end"] - rows[0]["start"] == 23*3600
    rows = p.date_windows({"window":"custom","start_date":"2026-11-01","end_date":"2026-11-01"}, {})
    assert rows[0]["end"] - rows[0]["start"] == 25*3600
    with pytest.raises(ValueError): p.date_windows({"window":"bad"},{})
    with pytest.raises(ValueError): p.date_windows({"window":"custom","start_date":"2026-02-02","end_date":"2026-02-01"},{})
    now = datetime(2026,1,31,tzinfo=ZoneInfo("America/Los_Angeles"))
    assert p.date_windows({}, {}, now) == []
    rows = p.date_windows({}, {"visit_days":["2026-01-01","2026-01-20","2026-02-01"]}, now)
    assert [r["id"] for r in rows] == ["current","previous"]
    assert rows[0]["start"] == rows[1]["end"]
    rows = p.date_windows({"window":"past28"},{},now)
    assert rows[0]["end"]-rows[0]["start"] == 28*86400


def test_native_home_exact_values_conflicts_and_missing():
    now = datetime(2026,1,31,tzinfo=ZoneInfo("America/Los_Angeles"))
    t0 = datetime(2026,1,25,tzinfo=ZoneInfo("America/Los_Angeles" )).timestamp()
    context = {"visit_days":["2026-01-01"],"home_intervals":[{"start":t0,"end":t0+2000}]}
    rows = [{"ChannelNames":["LeftHemisphere LFP"],"Time":[t0-600,t0,t0+600,t0+1200,float("nan"),t0+1800],"Data":[[1,1],[2,2],[3,-1],[4,4],[5,5]]},
            {"ChannelNames":["LeftHemisphere LFP"],"Time":[t0,t0+600],"Data":[[9,3],[3,-1]]},
            {"ChannelNames":["RightHemisphere LFP"],"Time":[t0],"Data":[[12]]},
            {"ChannelNames":[]},{"ChannelNames":["Unknown LFP"]}]
    def native(records, streaming):
        assert streaming == []
        r=records[0]
        # This is a canonical service contract fixture, not a reimplementation.
        channel = "ONE_THREE_LEFT" if r["ChannelNames"][0].startswith("Left") else "RightHemisphere LFP"
        return {channel:{"t":[r["Time"][0]],"y":[r["Data"][0][0]],"center_hz":[20 if channel.startswith("ONE") else None]}}
    def pairs(r, times, hemi, fallback): return ["ONE_THREE_LEFT" if hemi=="LEFT" else fallback]*len(times)
    result = p.home_timeline({},context,rows,native,pairs,now)
    assert result["status"] == "available"
    segments = result["windows"][0]["panels"][0]["segments"]
    points = [v for segment in segments for v in segment["points"]]
    # Overlapping exports with different native amplitudes are not averaged.
    assert any(x["time"] == t0 and x["amplitude_conflict"] and x["amplitude"] is None for x in points)
    assert any(x["power"] is None and x["amplitude"] == 4 for x in points)
    assert result["windows"][0]["panels"][1]["segments"][0]["mapping_status"] == "unknown"
    assert p.home_timeline({}, {}, [],native,pairs,now)["windows"] == []
    assert p.home_timeline({}, {"visit_days":["2026-01-01"]}, [],native,pairs,now)["status"] == "unavailable"


def test_home_conflicts_same_band_and_window_filter():
    t0 = datetime(2026,1,25,tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    rows = [{"ChannelNames":["LeftHemisphere LFP"],"Time":[t0,t0+86400],"Data":[[v,a],[v,a]]} for v,a in ((10,1),(20,2))]
    native = lambda records,pd: {"ONE_THREE_LEFT":{"t":records[0]["Time"],"y":[records[0]["Data"][0][0]]*2,"center_hz":[20,20]}}
    pairs = lambda r,t,h,f: ["ONE_THREE_LEFT"]*len(t)
    result = p.home_timeline({"window":"custom","start_date":"2026-01-25","end_date":"2026-01-25"}, {"home_intervals":[{"start":t0,"end":t0+200000}]},rows,native,pairs)
    points=result["windows"][0]["panels"][0]["segments"][0]["points"]
    assert points == [{"time":t0,"power":None,"power_conflict":True,"amplitude":None,"amplitude_conflict":True}]


def test_real_prasad_native_mapping_and_sentinel_agreement(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]))
    from modules.DecodeCommon import representation
    t0 = datetime(2026,1,25,tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    recording = {"ChannelNames":["LeftHemisphere LFP","LeftHemisphere Amplitude"],
                 "Time":[t0,t0+600,t0+1200,t0+1800],"Data":[[12,1],[2**31-1,2],[-1,3],[17,4]],
                 "ContactSchedule":[[t0,"1-3"]],"CenterFrequencyHz":20}
    canonical=representation.native_lsb_by_channel([recording],[])
    assert canonical["ONE_THREE_LEFT"]["y"] == [12.0,17.0]
    result=p.home_timeline({"window":"custom","start_date":"2026-01-25","end_date":"2026-01-25"},
        {"home_intervals":[{"start":t0,"end":t0+86400}]},[recording],representation.native_lsb_by_channel,representation.chronic_pair_keys)
    segments=result["windows"][0]["panels"][0]["segments"]
    assert len([segment for segment in segments if segment["center_frequency_hz"] is not None]) == 2
    points=[pt for segment in segments for pt in segment["points"]]
    assert sorted((pt["time"],pt["power"],pt["amplitude"]) for pt in points)==[(t0,12,1),(t0+600,None,2),(t0+1200,None,3),(t0+1800,17,4)]


def test_source_shaped_settings_programs_contacts_units_and_geometry():
    stimuli=[]
    for side,contact,amplitude,pw in (("Left","E01-A",1,60),("Left","E02-B",2,90),("Right","E01-C",3,120)):
        stimuli.append({"Electrode":{"Target":side+" VPL","Type":"SenSight B33015"},"Contact":[contact],"ReturnContact":["CAN"],
                        "Amplitude":amplitude,"AmplitudeUnit":"mA","Pulsewidth":pw,"PulsewidthUnit":"uS","Frequency":130,"Cycling":.25,"CyclingPeriod":12000})
    event=p.therapy_observations({"TherapyConfiguration":[{"History":[{"Date":100,"StimulationType":"Interleaving","StimulationSettings":stimuli}]}]})[0]
    left={r["label"]:r["value"] for r in event["settings"]["left"]}
    right={r["label"]:r["value"] for r in event["settings"]["right"]}
    group={r["label"]:r["value"] for r in event["settings"]["group"]}
    assert left["Program 1 · Stimulation contacts"]=="1a- C+"
    assert left["Program 2 · Stimulation contacts"]=="2b- C+"
    assert right["Stimulation contacts"]=="9c- C+"
    assert left["Program 1 · Pulse width"]=="60 µs"
    assert left["Program 2 · Pulse width"]=="90 µs"
    assert right["Pulse width"]=="120 µs"
    assert left["Program 1 · Source contacts"]=="E01-A → CAN"
    assert group["Cycling"]=="On · On 3 s / Off 9 s"
    assert group["Mode at observation"]=="Interleaving"
    assert event["lead_geometry"]=={"left":"sensight","right":"sensight"}


@pytest.mark.parametrize("stim,expected",[({},None),({"Cycling":1},"Off"),({"Cycling":2},"Unknown (invalid recorded duty fraction)"),
    ({"Cycling":.5},"Recorded duty fraction 0.5; period unit unverified"),
    ({"Cycling":.5,"Electrode":{"Type":"Medtronic 3389"}},"On"),
    ({"Cycling":.5,"CyclingPeriod":0,"Electrode":{"Type":"SenSight B33005"}},"On")])
def test_cycling_unknown_units_never_guessed(stim,expected):
    assert p._cycling(stim)==expected


@pytest.mark.parametrize("stim,side,expected",[
    ({},"left","Not recorded"),
    ({"Contact":["E01-A"]},"left","Unresolved source contacts"),
    ({"Contact":["E01-A"],"Electrode":{"Type":"Medtronic 3389"}},"left","Unresolved source contacts"),
    ({"Contact":["E00-A"],"Electrode":{"Type":"SenSight B33015"}},"left","Unresolved source contacts"),
    ({"Contact":["E00"],"ReturnContact":["E03"],"Electrode":{"Type":"Medtronic 3389"}},"right","8- 11+"),
    ({"Contact":["weird"],"Electrode":{"Type":"SenSight B33005"}},"left","Unresolved source contacts")])
def test_contact_conversion_preserves_uncertainty(stim,side,expected):
    assert p._contacts(stim,side)==expected


def test_conflicting_cycling_and_unknown_unit_preserved():
    stimuli=[{"Electrode":{"Target":"Left VPL","Type":"SenSight B33005"},"Cycling":1,"Pulsewidth":.06,"PulsewidthUnit":"ms"},
             {"Electrode":{"Target":"Right VPL","Type":"SenSight B33015"},"Cycling":.25,"CyclingPeriod":12000}]
    event=p.therapy_observations({"TherapyConfiguration":[{"History":[{"Date":100,"StimulationSettings":stimuli}]}]})[0]
    assert next(r["value"] for r in event["settings"]["group"] if r["label"]=="Cycling").startswith("Conflicting records")
    assert {r["label"]:r["value"] for r in event["settings"]["left"]}["Pulse width"]=="0.06 ms"


def test_home_half_open_envelopes_include_singletons_and_last_samples():
    from modules.DecodeCommon import representation
    t0=datetime(2026,1,25,tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    context={"home_intervals":[{"start":t0,"end":t0+86400}]}
    request={"window":"custom","start_date":"2026-01-25","end_date":"2026-01-25"}
    for data in ([[1,2]],[[1,2],[3,4]],[[1,2],[2**31-1,3],[4,5]]):
        recording={"ChannelNames":["LeftHemisphere LFP","LeftHemisphere Amplitude"],"Time":[t0+i*600 for i in range(len(data))],"Data":data}
        result=p.home_timeline(request,context,[recording],representation.native_lsb_by_channel,representation.chronic_pair_keys)
        window=result["windows"][0]
        visible=[pt for s in window["panels"][0]["segments"] for pt in s["points"] if s["start"]<=pt["time"]<s["end"]]
        assert len(visible)==len(data)
        assert all(s["end"]<=window["end"] and s["end_basis"]=="exclusive_sample_envelope" for s in window["panels"][0]["segments"])


def test_neural_scope_validates_server_context_and_bounds(monkeypatch, tmp_path):
    scope = {"coverage_start": 100, "coverage_end": 200, "description": " Historical testing-calendar coverage. "}
    context = {"neural_scope": scope, "home_intervals": [{"start": 100, "end": 200}]}
    assert p.neural_scope({}) is None
    assert p.neural_scope(context) == {**scope, "description": scope["description"].strip()}
    path = tmp_path / "context.json"
    path.write_text(json.dumps({"schema_version": 1, "participants": {"a": {"reviewed": True, "revision": "r", **context, "private": "never"}}}))
    monkeypatch.setenv("BRAVO_ADITYA_PRESENTATION_METADATA", str(path))
    assert "private" not in p.read_context("a")
    assert p.read_context("a")["neural_scope"] == scope


@pytest.mark.parametrize("scope", [None, [], {}, {"coverage_start": 1, "coverage_end": 2, "description": "d", "private": "secret"},
    {"coverage_start": True, "coverage_end": 2, "description": "d"},
    {"coverage_start": "1", "coverage_end": 2, "description": "d"},
    {"coverage_start": 1, "coverage_end": float("inf"), "description": "d"},
    {"coverage_start": 2, "coverage_end": 1, "description": "d"},
    *[{"coverage_start": 1, "coverage_end": 2, "description": d} for d in (None, " ", "d" * 501, "hidden\nline")]])
def test_neural_scope_rejects_malformed_and_private_fields(scope):
    with pytest.raises(ValueError):
        p.neural_scope({"neural_scope": scope})


@pytest.mark.parametrize("interval", [None, {}, {"start": 1, "end": 2, "extra": "no"},
    {"start": True, "end": 2}, {"start": "1", "end": 2}, {"start": 1, "end": float("nan")},
    {"start": 0, "end": 2}, {"start": 1, "end": 3}, {"start": 2, "end": 2}])
def test_neural_scope_rejects_intervals_outside_half_open_coverage(interval):
    with pytest.raises(ValueError):
        p.neural_scope({"neural_scope": {"coverage_start": 1, "coverage_end": 2, "description": "d"}, "home_intervals": [interval]})


def test_window_coverage_preserves_requested_dates_and_exclusive_end():
    scope = {"coverage_start": 100, "coverage_end": 200, "description": "d"}
    for window, expected in [({"start": 200, "end": 300}, {"status": "outside", "start": None, "end": None}),
                             ({"start": 0, "end": 100}, {"status": "outside", "start": None, "end": None}),
                             ({"start": 100, "end": 200}, {"status": "covered", "start": 100, "end": 200}),
                             ({"start": 50, "end": 150}, {"status": "partial", "start": 100, "end": 150})]:
        before = dict(window)
        assert p.window_coverage(window, scope) == expected
        assert window == before


def test_home_scope_reports_current_outside_previous_supported_without_retargeting():
    now = datetime(2026, 10, 17, tzinfo=ZoneInfo("America/Los_Angeles"))
    start = datetime(2026, 9, 30, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    end = datetime(2026, 10, 7, tzinfo=ZoneInfo("America/Los_Angeles")).timestamp()
    context = {"visit_days": ["2026-09-30", "2026-10-07"], "home_intervals": [{"start": start, "end": end}],
               "neural_scope": {"coverage_start": start, "coverage_end": end, "description": "Historical testing-calendar coverage."}}
    result = p.home_timeline({}, context, [], lambda *_: {}, lambda *_: [], now=now)
    assert result["windows"][0]["start"] == end
    assert result["windows"][0]["coverage"]["status"] == "outside"
    assert result["windows"][1]["coverage"] == {"status": "covered", "start": start, "end": end}
    assert result["neural_scope"] == context["neural_scope"]
    missing_intervals = dict(context, home_intervals=[])
    assert p.home_timeline({}, missing_intervals, [], None, None, now=now)["neural_scope"] == context["neural_scope"]


def observation_context(start, end, reviewed_start=None, reviewed_end=None, days=()):
    reviewed_start = start - 86400 if reviewed_start is None else reviewed_start
    reviewed_end = start if reviewed_end is None else reviewed_end
    return {"revision": "synthetic-reviewed", "visit_days": list(days),
            "neural_scope": {"coverage_start": reviewed_start, "coverage_end": reviewed_end, "description": "Reviewed context"},
            "home_intervals": [{"start": reviewed_start, "end": reviewed_end}],
            "neural_observation_scope": {"start": start, "end": end, "description": " Recorded observations; location unverified. "}}


def observational_recording(times, values=None):
    return {"ChannelNames": ["LEFT synthetic"], "Time": times,
            "Data": [[value, value] for value in (values if values is not None else range(len(times)))],
            "Therapy": []}


def synthetic_native(recordings, streams):
    assert streams == []
    row = recordings[0]
    return {"LEFT_0-2": {"t": row['Time'], "y": [v[0] for v in row['Data']], "center_hz": [20] * len(row['Time'])}}


def synthetic_pairs(recording, times, hemi, name):
    return ["LEFT_0-2"] * len(times)


def test_observation_wrapper_preserves_home_payload_and_adds_exact_recent_samples():
    import copy, math
    start = datetime(2026, 10, 8, tzinfo=p.PACIFIC).timestamp()
    context = observation_context(start, start + 86400 * 20, days=['2026-10-07'])
    request = {'window': 'past28'}
    now = datetime(2026, 10, 17, tzinfo=p.PACIFIC)
    recent = start + 1200
    rows = [observational_recording([start - 1200, recent, recent + 600, recent + 1800], [3, 0, None, 5])]
    original = copy.deepcopy((context, rows, request))
    historical = p.home_timeline(request, context, rows, synthetic_native, synthetic_pairs, now)
    result = p.neural_timeline(request, context, rows, synthetic_native, synthetic_pairs, now)
    assert {key: result[key] for key in historical} == historical
    assert json.dumps({key: result[key] for key in historical}, separators=(',', ':')) == json.dumps(historical, separators=(',', ':'))
    assert (context, rows, request) == original
    assert result['observation_scope']['description'] == context['neural_observation_scope']['description'].strip()
    window = result['observation_windows'][0]
    assert (window['start'], window['end']) == (historical['windows'][0]['start'], historical['windows'][0]['end'])
    assert window['coverage'] == {'status': 'partial', 'start': recent, 'end': math.nextafter(recent + 1800, math.inf)}
    assert window['coverage']['end'] < context['neural_observation_scope']['end']
    assert window['display_basis'] == 'recorded_observations' and window['coverage_basis'] == 'recorded_sample_envelope'
    segments = window['panels'][0]['segments']
    assert len(segments) == 2
    assert [point['power'] for segment in segments for point in segment['points']] == [0, None, 5]
    assert [point['amplitude'] for segment in segments for point in segment['points']] == [0, None, 5]
    for segment in segments:
        assert segment['mode'] == 'unknown' and segment['thresholds'] == []
        assert segment['mapping_status'] == 'unknown'
        assert 'Physical home/location and testing-calendar completeness are unverified' in segment['evidence']
        assert 'reviewed home eligibility' not in segment['evidence']
        assert segment['end'] == math.nextafter(segment['points'][-1]['time'], math.inf)
    assert window['panels'][1]['segments'] == []


@pytest.mark.parametrize('scope', [None, [], {}, {'start': 1, 'end': 2, 'description': 'd', 'private': 'never'},
    {'start': True, 'end': 2, 'description': 'd'}, {'start': '1', 'end': 2, 'description': 'd'},
    {'start': 1, 'end': float('inf'), 'description': 'd'}, {'start': 1, 'end': float('nan'), 'description': 'd'},
    {'start': 2, 'end': 1, 'description': 'd'}, {'start': 1, 'end': 1, 'description': 'd'},
    *[{'start': 1, 'end': 2, 'description': value} for value in (None, '', ' ', 'd' * 501, 'hidden\nvalue')]])
def test_observation_scope_rejects_ambiguous_bounds_and_private_fields(scope):
    context = observation_context(1, 2); context['neural_observation_scope'] = scope
    with pytest.raises(ValueError): p.neural_observation_scope(context)


@pytest.mark.parametrize('missing', ['neural_scope', 'home_intervals'])
def test_observation_scope_requires_reviewed_context(missing):
    context = observation_context(100, 200); context.pop(missing)
    with pytest.raises(ValueError, match='reviewed home context'): p.neural_observation_scope(context)


def test_observation_scope_disjoint_before_or_after_and_participant_private_context(monkeypatch, tmp_path):
    context = observation_context(100, 200, reviewed_start=200, reviewed_end=300)
    assert p.neural_observation_scope(context)['start'] == 100
    context['neural_scope']['coverage_start'] = 150
    context['home_intervals'][0]['start'] = 150
    with pytest.raises(ValueError, match='overlaps'): p.neural_observation_scope(context)
    context = observation_context(100, 200)
    path = tmp_path / 'context.json'
    path.write_text(json.dumps({'schema_version': 1, 'participants': {'a': dict(context, reviewed=True), 'b': {'reviewed': False}}}))
    monkeypatch.setenv('BRAVO_ADITYA_PRESENTATION_METADATA', str(path))
    assert p.read_context('a')['neural_observation_scope'] == context['neural_observation_scope']
    assert p.read_context('b') == {}
    legacy = dict(context); legacy.pop('neural_observation_scope')
    assert p.neural_observation_scope(legacy) is None
    request = {'window': 'past28'}
    assert p.neural_timeline(request, legacy, [], None, None) == p.home_timeline(request, legacy, [], None, None)


@pytest.mark.parametrize('day,hours', [('2026-03-08', 23), ('2026-11-01', 25)])
def test_observations_exclude_documented_days_and_both_inclusive_margins_across_dst(day, hours):
    import math
    from datetime import date, time, timedelta
    begin = datetime.combine(date.fromisoformat(day), time.min, p.PACIFIC).timestamp()
    finish = datetime.combine(date.fromisoformat(day) + timedelta(days=1), time.min, p.PACIFIC).timestamp()
    assert finish - begin == hours * 3600
    low, high = begin - 600, finish + 600
    context = observation_context(low - 100, high + 100, days=[day, day])
    times = [math.nextafter(low, -math.inf), low, begin, finish, high, math.nextafter(high, math.inf)]
    rows = [observational_recording(times)]
    result = p.neural_timeline({'window': 'custom', 'start_date': (date.fromisoformat(day)-timedelta(days=1)).isoformat(),
        'end_date': (date.fromisoformat(day)+timedelta(days=1)).isoformat()}, context, rows, synthetic_native, synthetic_pairs)
    points = [point for panel in result['observation_windows'][0]['panels'] for segment in panel['segments'] for point in segment['points']]
    assert [point['time'] for point in points] == [times[0], times[-1]]


def test_observation_interval_clipping_and_empty_rendering():
    from datetime import date, time, timedelta
    day = '2026-01-10'; low = datetime.combine(date.fromisoformat(day), time.min, p.PACIFIC).timestamp() - 600
    high = datetime.combine(date.fromisoformat(day)+timedelta(days=1), time.min, p.PACIFIC).timestamp() + 600
    assert p.observation_intervals({'start': low+1, 'end': high}, [day]) == []
    assert p.observation_intervals({'start': low-1, 'end': low}, [day]) == [{'start':low-1,'end':low}]
    assert p.observation_intervals({'start': high+1, 'end': high+2}, [day]) == [{'start':high+1,'end':high+2}]
    context = observation_context(low+1, high, days=[day])
    assert p.neural_timeline({'window':'past28'},context,[],None,None)['observation_windows'] == []
    context = observation_context(low-1000, low+1000, days=[day])
    assert p.neural_timeline({'window':'custom','start_date':'2026-01-10','end_date':'2026-01-10'},
        context,[observational_recording([low-1])],synthetic_native,synthetic_pairs)['observation_windows'] == []
    with pytest.raises(ValueError): p.observation_intervals({'start':low,'end':high},['not-a-day'])


def test_observation_visits_preserve_requested_ids_and_keep_historical_period_separate():
    start = datetime(2026,10,7,tzinfo=p.PACIFIC).timestamp()
    context = observation_context(start,start+86400*20,days=['2026-09-30','2026-10-07'])
    rows=[observational_recording([start-1200,start+86400+601])]
    now=datetime(2026,10,17,tzinfo=p.PACIFIC)
    result=p.neural_timeline({},context,rows,synthetic_native,synthetic_pairs,now)
    assert [window['id'] for window in result['windows']]==['current','previous']
    assert [window['id'] for window in result['observation_windows']]==['current']
    assert result['observation_windows'][0]['start']==result['windows'][0]['start']
    assert result['observation_windows'][0]['coverage']['start']==rows[0]['Time'][1]
    assert result['windows'][0]['coverage']['status']=='outside'


def test_observation_uses_real_native_channels_sentinels_and_half_open_scope():
    import math
    from modules.DecodeCommon import representation
    start=datetime(2026,1,25,tzinfo=p.PACIFIC).timestamp()
    context=observation_context(start,start+1800)
    recording={'ChannelNames':['LeftHemisphere LFP','LeftHemisphere Amplitude'],
        'Time':[start-600,start,start+600,start+1200,start+1800],
        'Data':[[9,9],[0,0],[2**31-1,2],[-1,3],[17,4]],
        'ContactSchedule':[[start-600,'1-3']], 'CenterFrequencyHz':20}
    result=p.neural_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},context,
        [recording],representation.native_lsb_by_channel,representation.chronic_pair_keys)
    window=result['observation_windows'][0]
    points=[point for panel in window['panels'] for segment in panel['segments'] for point in segment['points']]
    assert sorted((point['time'],point['power'],point['amplitude']) for point in points)==[(start,0,0),(start+600,None,2),(start+1200,None,3)]
    assert window['coverage']['end']==math.nextafter(start+1200,math.inf)<start+1800
    assert all(segment['sensing_contacts']=='ONE_THREE_LEFT' for segment in window['panels'][0]['segments'])
    assert all(segment['mapping_status']=='unknown' for segment in window['panels'][0]['segments'])
    assert all(segment['thresholds']==[] and segment['mode']=='unknown' for segment in window['panels'][0]['segments'])


def auto_context(start):
    context = observation_context(start, start+100)
    context['neural_observation_scope'] = {'mode':'automatic','description':'Unverified observations'}
    return context


def test_automatic_advances_actual_samples_preserving_original_home_and_exclusions():
    import copy, math
    start = datetime(2026,10,8,tzinfo=p.PACIFIC).timestamp()
    context = auto_context(start)
    context['visit_days'] = ['2026-10-09']
    now = datetime(2026,10,18,tzinfo=p.PACIFIC)
    calendar = {'status':'stored_snapshot','days':['2026-10-10','2026-10-11'],
                'clinic_days':['2026-10-10'],'built_at':'2026-10-17T00:00:00+00:00'}
    rows = [observational_recording([start-1200,start+1200,start+86400+1200,start+2*86400+1200,
                                   start+3*86400+1200,start+4*86400+1200,now.timestamp()+600])]
    before=copy.deepcopy(context)
    request={'window':'custom','start_date':'2026-10-07','end_date':'2026-10-19'}
    historical=p.home_timeline(request,context,rows,synthetic_native,synthetic_pairs,now)
    result=p.neural_timeline(request,context,rows,synthetic_native,synthetic_pairs,now,calendar)
    assert {k:result[k] for k in historical}==historical and context==before
    points=[v for w in result['observation_windows'] for panel in w['panels'] for seg in panel['segments'] for v in seg['points']]
    assert [v['time'] for v in points]==[start+1200,start+4*86400+1200]
    assert result['observation_scope']['end']==math.nextafter(start+4*86400+1200,math.inf)
    assert result['observation_provenance']['freshness']=='upstream_unverified'
    rows[0]['Time'].append(start+5*86400+1200);rows[0]['Data'].append([9,0])
    advanced=p.neural_timeline(request,context,rows,synthetic_native,synthetic_pairs,now,calendar)
    assert advanced['observation_scope']['end']>result['observation_scope']['end']
    scope,excluded,anchors,_=p.automatic_observations(context,rows,calendar,now)
    assert excluded==['2026-10-09','2026-10-10','2026-10-11'] and anchors==['2026-10-10']


@pytest.mark.parametrize('calendar',[None,{'status':'invalid'},{'status':'unavailable'}])
def test_automatic_calendar_failure_keeps_historical_output(calendar):
    context=auto_context(100)
    result=p.neural_timeline({},context,[],None,None,calendar=calendar)
    assert result['observation_windows']==[] and 'observation_scope' not in result
    assert result['observation_provenance']['calendar_status'] in ('invalid','unavailable')
    assert result['windows']==p.home_timeline({},context,[],None,None)['windows']


def test_automatic_rejects_future_and_invalid_timestamps_and_no_recent_data():
    context=auto_context(100)
    calendar={'status':'stored_snapshot','days':[],'clinic_days':[]}
    now=datetime.fromtimestamp(200,p.PACIFIC)
    for times in ([],[99,None,True,'150',float('nan'),float('inf'),201]):
        assert p.automatic_observations(context,[{'Time':times}],calendar,now)[0] is None
    assert p.automatic_observations(context,[{'Time':[100,200]}],calendar,now)[0]['end']>200
    assert p.neural_observation_scope(context)==context['neural_observation_scope']
    context['neural_observation_scope']['description']=' '
    with pytest.raises(ValueError):p.neural_observation_scope(context)
    context['neural_observation_scope']['description']='ok'
    context.pop('home_intervals')
    with pytest.raises(ValueError):p.neural_observation_scope(context)


def clinic_fixture():
    stamp={'kind':'clinic_pain_steps','participant_uid':'a','signature_key':'a'*40,'written_utc':'2026-10-17T00:00:00+00:00'}
    receipt={'format':1,'target_participant_uid':'a','canonical_store_key':'clinic_pain_steps/a/'+'a'*40,
             'repeat_wrote':False,'workbook_files':2,'parsed_steps':1}
    manifest=[{'file':'10_10_26-clinic','setting':'clinic','error':None},
              {'file':'10_11_26-home','setting':'home','error':''}]
    steps=[{'file':'10_10_26-clinic','setting':'clinic','visit_date_ts':datetime(2026,10,10,tzinfo=p.PACIFIC),'sha256':'a'*64}]
    parse=lambda name:datetime.strptime(name[:8],'%m_%d_%y').replace(tzinfo=p.PACIFIC)
    infer=lambda name:'home' if 'home' in name else 'clinic'
    return manifest,steps,stamp,receipt,'a',parse,infer,datetime(2026,10,18,tzinfo=p.PACIFIC).timestamp()


def test_clinic_calendar_complete_manifest_includes_zero_step_home_workbook():
    args=clinic_fixture();out=p.clinic_calendar(*args)
    assert out=={'status':'stored_snapshot','days':['2026-10-10','2026-10-11'],
                 'clinic_days':['2026-10-10'],'built_at':'2026-10-17T00:00:00+00:00'}


@pytest.mark.parametrize('target,key,value',[
 ('stamp','signature_key',None),('stamp','signature_key','invalid'),('receipt','format',True),
 ('receipt','workbook_files',True),('receipt','parsed_steps',True),
 ('stamp','kind','other'),('stamp','participant_uid','b'),('receipt','format',2),
 ('receipt','target_participant_uid','b'),('receipt','repeat_wrote',True),('receipt','canonical_store_key','wrong'),
 ('stamp','written_utc','2026-10-17'),('stamp','written_utc','2027-01-01T00:00:00+00:00'),
 ('receipt','workbook_files',3),('receipt','parsed_steps',2),
 ('manifest','setting','bad'),('manifest','setting','home'),('manifest','error','parse failed'),
 ('steps','file','unknown'),('steps','setting','home'),('steps','sha256','bad'),
 ('steps','sha256',None),('steps','visit_date_ts',None),('steps','visit_date_ts','2026-10-10')])
def test_clinic_calendar_invalid_snapshot_fails_closed(target,key,value):
    args=list(clinic_fixture());indexes={'manifest':0,'steps':1,'stamp':2,'receipt':3}
    obj=args[indexes[target]]
    if isinstance(obj,list):obj=obj[0]
    obj[key]=value
    with pytest.raises(ValueError):p.clinic_calendar(*args)


def test_clinic_calendar_duplicate_missing_future_and_conflicting_rows():
    import copy
    for mode in ('empty','duplicate','missingdate','conflict'):
        args=list(clinic_fixture())
        if mode=='empty':args[0]=[]
        if mode=='duplicate':args[0][1]=dict(args[0][0])
        if mode=='missingdate':args[5]=lambda name:None
        if mode=='conflict':
            args[1].append({**args[1][0],'sha256':'b'*64});args[3]['parsed_steps']=2
        with pytest.raises(ValueError):p.clinic_calendar(*args)


def test_future_planned_calendar_dates_conservatively_exclude_without_invalidating_snapshot():
    args=list(clinic_fixture())
    args[0][1]['file']='01_01_27-home'
    calendar=p.clinic_calendar(*args)
    assert calendar['days']==['2026-10-10','2027-01-01']
    assert calendar['clinic_days']==['2026-10-10']


def test_automatic_visit_windows_use_stored_clinic_anchors_never_reviewed_labels():
    start=datetime(2026,10,8,tzinfo=p.PACIFIC).timestamp()
    context=auto_context(start)
    context['visit_days']=['2026-10-07']
    calendar={'status':'stored_snapshot','days':['2026-10-10','2026-10-15'],
              'clinic_days':['2026-10-10','2026-10-15']}
    rows=[observational_recording([start+3*86400+1200,start+8*86400+1200])]
    result=p.neural_timeline({},context,rows,synthetic_native,synthetic_pairs,datetime(2026,10,18,tzinfo=p.PACIFIC),calendar)
    assert [w['label'] for w in result['observation_windows']]==['Since latest stored clinic date','Between stored clinic dates']
    assert result['windows'][0]['label']=='Since latest reviewed visit'

@pytest.mark.parametrize('value', [None, {}, 'missing', [None], [[1]], [[1,2,3]], [[None,2]], [[True,2]], [[1,False]], [[1,'bad']], [[2,2]], [[2,1]], [[float('nan'),3]], [[1,float('inf')]]])
def test_schedule_interval_malformed_is_unverified(value):
    assert p._schedule_intervals(value) is None


def test_schedule_interval_empty_and_open_ended_are_distinct_from_missing():
    assert p._schedule_intervals([]) == []
    assert p._schedule_intervals([[1,None],[2,3]]) == [(1,None),(2,3)]
    assert p._sensing_provenance([(True,False,False)])['status'] == 'recorded'
    assert p._sensing_provenance([(False,False,False)])['status'] == 'unverified'
    assert p._sensing_provenance([(True,True,False)])['conflicting_settings'] is True
    assert p._sensing_provenance([(True,False,True)])['inherited_settings'] is True


def test_neural_schedule_provenance_splits_half_open_intervals_without_changing_measurements():
    t0 = datetime(2026,1,25,tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    times=[t0+i*600 for i in range(5)]
    recording={'ChannelNames':['LeftHemisphere LFP'], 'Time':times,'Data':[[10+i,0] for i in range(5)],
        'ScheduleFlagged':[[t0+600,t0+1200]],'ScheduleNoRecord':[[t0+1800,None]],
        'ChronicAnalysisPolicy':dict(p.CHRONIC_ANALYSIS_POLICY)}
    native=lambda records,pd:{'ONE_THREE_LEFT':{'t':times,'y':[10,11,12,13,14],'center_hz':[20]*5}}
    pairs=lambda r,t,h,f:['ONE_THREE_LEFT']*len(t)
    result=p.home_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},
        {'home_intervals':[{'start':t0,'end':t0+6000}]},[recording],native,pairs)
    segments=result['windows'][0]['panels'][0]['segments']
    assert [len(segment['points']) for segment in segments] == [1,1,1,2]
    assert [segment['sensing_provenance']['status'] for segment in segments] == ['recorded','unverified','recorded','unverified']
    assert segments[1]['sensing_provenance']['conflicting_settings'] is True
    assert segments[-1]['sensing_provenance']['inherited_settings'] is True
    assert all(segment['sensing_side']=='left' and segment['center_frequency_hz']==20 for segment in segments)
    assert [point['power'] for segment in segments for point in segment['points']] == [10,11,12,13,14]
    assert all(point['amplitude']==0 for segment in segments for point in segment['points'])
    assert result['chronic_analysis_policy'] == p.CHRONIC_ANALYSIS_POLICY


def test_duplicate_schedule_evidence_is_conservative_without_duplicating_points():
    t0 = datetime(2026,1,25,tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    base={'ChannelNames':['LeftHemisphere LFP'],'Time':[t0],'Data':[[12,1]],'ScheduleFlagged':[],'ScheduleNoRecord':[]}
    records=[base,{**base,'ScheduleFlagged':[[t0,None]]},{k:v for k,v in base.items() if k!='ScheduleNoRecord'}]
    native=lambda records,pd:{'ONE_THREE_LEFT':{'t':[t0],'y':[12],'center_hz':[20]}}
    pairs=lambda *args:['ONE_THREE_LEFT']
    result=p.home_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},
        {'home_intervals':[{'start':t0,'end':t0+1000}]},records,native,pairs)
    segments=result['windows'][0]['panels'][0]['segments']
    assert len(segments)==1 and len(segments[0]['points'])==1
    assert segments[0]['sensing_provenance']=={'status':'unverified','metadata_available':False,'conflicting_settings':True,'inherited_settings':False}
    assert 'chronic_analysis_policy' not in result


def test_chronic_zero_policy_is_shared_analysis_exclusion_raw_and_zero_current_preserved(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]))
    from modules.DecodeCommon import representation
    import numpy as np
    t0=datetime(2026,1,25,tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    raw={'ChannelNames':['LeftHemisphere LFP','LeftHemisphere Amplitude'],'Time':[t0,t0+600,t0+1200],
        'Data':[[0,0],[12,0],[2**31-1,2]],'ContactSchedule':[[t0,'1-3']], 'CenterFrequencyHz':20,
        'ScheduleFlagged':[],'ScheduleNoRecord':[],'ChronicAnalysisPolicy':dict(p.CHRONIC_ANALYSIS_POLICY)}
    original=np.array(raw['Data'],dtype=float)
    prepared,counts=representation.merge_chronic_repeats([raw])
    result=p.home_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},
        {'home_intervals':[{'start':t0,'end':t0+2000}]},prepared,representation.native_lsb_by_channel,representation.chronic_pair_keys)
    points=sorted([point for segment in result['windows'][0]['panels'][0]['segments'] for point in segment['points']],key=lambda point:point['time'])
    assert [point['power'] for point in points]==[None,12,None]
    assert [point['amplitude'] for point in points]==[0,0,2]
    assert counts['zero_values']==1 and counts['invalid_code_values']==1
    np.testing.assert_array_equal(raw['Data'],original)
    assert result['chronic_analysis_policy']['raw_values_preserved'] is True


def test_canonical_current_is_independent_of_moved_power_and_preserves_ambiguity():
    from modules.DecodeCommon import representation
    from modules.Biomarkers.routines import availability
    t0=datetime(2026,1,25,tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    own={'ChannelNames':['LeftHemisphere LFP','LeftHemisphere Amplitude'],'Time':[t0,t0+600,t0+1200],
         'Data':[[12,0],[14,1],[16,2]],'ContactSchedule':[[t0,'1-3']], 'CenterFrequencyHz':20}
    moved={**own,'ChannelNames':['RightHemisphere LFP','RightHemisphere Amplitude'],
           'Data':[[12,2],[14,3],[16,4]],'SignalLeadSchedule':[[t0,'LEFT']]}
    conflict={**moved,'Time':[t0+600],'Data':[[14,5]]}
    prepared,_=representation.merge_chronic_repeats([own,moved,conflict])
    result=p.home_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},
        {'home_intervals':[{'start':t0,'end':t0+2000}]},prepared,representation.native_lsb_by_channel,
        representation.chronic_pair_keys,stim_series=availability.stim_series)
    left,right=result['windows'][0]['panels']
    assert [point['amplitude'] for point in left['amplitude_series']]==[0,1,2]
    assert [point['amplitude'] for point in right['amplitude_series']]==[2,None,4]
    assert right['segments']==[]
    assert 'opposite-lead sensing' in right['amplitude_provenance']
    assert [point['power'] for segment in left['segments'] for point in segment['points']]==[12,14,16]


def test_current_timestamps_missing_conflicts_and_eligibility_are_not_aligned_to_power():
    t0=datetime(2026,1,25,tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
    series=lambda recordings,hemisphere: {'t':[None,t0-1,t0,t0,t0+10,t0+20,t0+30,t0+30,t0+40],
        'y':[9,9,1,2,None,-2,0,0,9]} if hemisphere=='Left' else {'t':[],'y':[]}
    result=p.home_timeline({'window':'custom','start_date':'2026-01-25','end_date':'2026-01-25'},
        {'home_intervals':[{'start':t0,'end':t0+40}]},[],lambda *a:{},lambda *a:[],stim_series=series)
    left,right=result['windows'][0]['panels']
    assert left['segments']==right['segments']==[]
    assert [point['amplitude'] for point in left['amplitude_series']]==[None,None,None,0]
    assert left['amplitude_series'][0]['amplitude_conflict'] is True
    assert right['amplitude_series']==[]
