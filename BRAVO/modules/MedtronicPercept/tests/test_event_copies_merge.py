"""Synthetic event-copy identity, contact ambiguity, and ingestion regressions."""
import ast
import copy
from unittest.mock import patch
from copy import deepcopy
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace

import pytest
from modules.MedtronicPercept.BrainSenseEvent import (
    mergeEventData, _usable_sense_id, saveBrainSenseEvents,
    extractBrainSenseEventRecording,
)

L = "HemisphereLocationDef.Left"
R = "HemisphereLocationDef.Right"


def side(power=(1, 2), sense="ZERO_THREE_LEFT"):
    return {"Frequency": [1.0, 2.0], "FFTBinData": list(power), "SenseID": sense}


def test_create_drop_attach_and_symmetric_side_union():
    for empty in (None, {}, {"note": "no spectrum"}):
        assert mergeEventData(None, empty)[0] == "drop"
    action, first, conflicts = mergeEventData(None, {L: side(), "note":"kept"})
    assert action == "create" and conflicts == [] and first["note"] == "kept"
    assert first[L]["FFTBinData"] == [1,2]
    assert first[L]["SenseID"] == "ZERO_THREE_LEFT"
    assert first[L]["SenseIDStatus"] == "resolved"
    assert mergeEventData({}, {L: side()})[0] == "update"
    action, both, conflicts = mergeEventData(first, {R: side(sense="ZERO_THREE_RIGHT"),"note":"ignored"})
    assert action == "update" and set(both)=={L,R,"note"} and both["note"]=="kept"
    assert mergeEventData(both,{L:side(),R:side(sense="ZERO_THREE_RIGHT")})[0]=="keep"
    assert mergeEventData(both,None)[0]=="keep"


@pytest.mark.parametrize("missing",[None,"", "NOT_SET", "SenseIDDef.NOT_SET", "  not_set  ", 42])
def test_unavailable_contact_enrichment_is_order_independent(missing):
    a,b={L:side(sense=missing)},{L:side()}
    _, ab, conflicts = mergeEventData(a,b)
    _, ba, reverse_conflicts = mergeEventData(b,a)
    assert ab==ba and conflicts==reverse_conflicts==[]
    assert ab[L]["SenseID"]=="ZERO_THREE_LEFT"
    assert ab[L]["SenseIDStatus"]=="resolved"
    assert {str(x["sense_id"]) for x in ab[L]["SenseIDObservations"]}=={str(missing),"ZERO_THREE_LEFT"}
    assert mergeEventData(ab,a)[0]==mergeEventData(ab,b)[0]=="keep"


def test_not_set_only_remains_unresolved_without_rewriting_raw_claim():
    _,data,_=mergeEventData(None,{L:side(sense="SenseIDDef.NOT_SET")})
    assert data[L]["SenseID"]=="" and data[L]["SenseIDStatus"]=="unresolved"
    assert data[L]["SenseIDObservations"]==[{"sense_id":"SenseIDDef.NOT_SET"}]
    assert _usable_sense_id(" ZERO_THREE_LEFT ")=="ZERO_THREE_LEFT"


def test_conflicting_contact_claims_preserved_in_all_import_orders():
    copies=[({L:side(sense=sense)}, {"source_id":str(i),"read_all_status":status}) for i,(sense,status) in enumerate(
        [("ZERO_THREE_LEFT","NOT_STARTED"),("ONE_THREE_LEFT","COMPLETED"),("NOT_SET","COMPLETED")])]
    final=[]
    originals=deepcopy(copies)
    for ordered in permutations(copies):
        merged=None
        for data,source in ordered:
            _,merged,conflicts=mergeEventData(merged,data,incoming_source=source)
        final.append(merged)
        assert conflicts==[L]
        assert merged[L]["SenseID"]=="" and merged[L]["SenseIDStatus"]=="ambiguous" and merged[L]["SenseIDConflict"]
        assert merged[L]["FFTBinData"]==[1,2] and merged[L]["Frequency"]==[1.,2.]
        assert len(merged[L]["SenseIDObservations"])==3
        for data,source in ordered:
            action,again,flags=mergeEventData(merged,data,incoming_source=source)
            assert action=="keep" and again==merged and flags==[L]
    assert all(item==final[0] for item in final) and copies==originals
    assert mergeEventData(None, final[0])[2]==[L]


@pytest.mark.parametrize("incoming",[side(power=(9,9)),{"Frequency":[1,3],"FFTBinData":[1,2],"SenseID":"ONE_THREE_LEFT"}])
def test_spectral_disagreement_existing_policy_unchanged(incoming):
    stored={L:side()}
    action,merged,conflicts=mergeEventData(stored,{L:incoming})
    assert action=="keep" and merged==stored and conflicts==[L]


def test_source_provenance_enrichment_and_nested_input_immutability():
    a,b={L:side()},{L:side(sense="ONE_THREE_LEFT")}
    source_a={"source_id":"a","source_hash":"hash-a"}; source_b={"source_id":"b","source_hash":"hash-b"}
    originals=deepcopy((a,b,source_a,source_b))
    _,merged,_=mergeEventData(a,b,stored_source=source_a,incoming_source=source_b)
    assert {x["source"]["source_id"] for x in merged[L]["SenseIDObservations"]}=={"a","b"}
    merged[L]["SenseIDObservations"][0]["source"]["source_id"]="changed"
    assert (a,b,source_a,source_b)==originals


def test_raw_event_display_retains_ambiguous_spectrum():
    _,data,_=mergeEventData({L:side()},{L:side(sense="ONE_THREE_LEFT")})
    device=SimpleNamespace(get_info=lambda:{"Heritage":[],"Electrodes":[{"Target":"Left lead","CustomName":"L lead"}]})
    devices=SimpleNamespace(filter=lambda **kw:SimpleNamespace(first=lambda:device))
    displayed=extractBrainSenseEventRecording({"Device":"synthetic","Metadata":data,"Date":100},devices)
    assert displayed[0]["Power"]==[1,2] and displayed[0]["SenseConfig"]==""
    assert displayed[0]["ChannelName"]=="L lead"
    assert displayed[0]["SenseConfigStatus"]=="ambiguous" and displayed[0]["SenseConfigConflict"]
    data[R]=side(sense="ZERO_THREE_RIGHT")
    assert extractBrainSenseEventRecording({"Device":"synthetic","Metadata":data,"Date":100},devices)[1]["ChannelName"]==R
    events=saveBrainSenseEvents([{"DateTime":datetime(2026,1,1,tzinfo=timezone.utc),"EventName":"Synthetic","LfpFrequencySnapshotEvents":data},
                                {"DateTime":datetime(2026,1,1,tzinfo=timezone.utc),"EventName":"Absent"}])
    assert events[0]["data"]==data and "data" not in events[1]


def ingestion_harness(connection=None, helpers=None):
    """Run the exact caller in an in-memory fake ORM; no Django/services/data writes."""
    events=[]
    class Record:
        def __init__(self, **kwargs): self.__dict__.update(kwargs); self.metadata={}; self.saves=0; self.uid="record"
        def save(self): self.saves+=1
    class Relation:
        def __init__(self): self.rows=[]
        def first(self): return self.rows[0] if self.rows else None
        def add(self,record): self.rows.append(record)
    class Event:
        def __init__(self,**kwargs): self.__dict__.update(kwargs); self.data=Relation()
        def save(self): events.append(self)
    Event.objects=SimpleNamespace(filter=lambda **kw:SimpleNamespace(first=lambda:events[0] if events else None))
    Record._meta=SimpleNamespace(db_table="synthetic_recording")
    models=SimpleNamespace(DBSEvent=Event,Recording=Record,SourceFile=SimpleNamespace(find=lambda **kw:None))
    path=Path(__file__).parents[2]/"DataCurator.py"
    function=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="_store_patient_event")
    namespace={**(helpers or {}),"models":models,"copy":copy}
    helper=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="_event_source_provenance")
    exec(compile(ast.Module(body=[helper],type_ignores=[]),str(path),"exec"),namespace)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),"exec"),namespace)
    def store(*args,**kwargs):
        with patch("django.db.connections", {"default":connection or SimpleNamespace(vendor="sqlite")}):
            return namespace["_store_patient_event"](*args,**kwargs)
    return store,events,Event


def source(uid,status):
    return SimpleNamespace(uid=uid,hashed="hash-"+uid,metadata={"ReadAllStatus":status,"FullyReadForSession":True})


def test_ingestion_create_update_conflict_receipts_and_repeat_idempotency():
    final=[]
    for ordered in (("partial","completed"),("completed","partial")):
        store,events,_=ingestion_harness()
        sources={"partial":source("partial","NOT_STARTED"),"completed":source("completed","COMPLETED")}
        copies={"partial":side(),"completed":side(sense="ONE_THREE_LEFT")}
        event={"date":100,"type":"PatientControllerEvent","name":"Synthetic"}
        assert store(event,sources[ordered[0]],"person")=="drop"
        for index,key in enumerate(ordered):
            assert store(dict(event,data={L:copies[key]}),sources[key],"person")==("create" if index==0 else "update")
        final.append(events[0].data.first().metadata)
        for key in ordered:
            assert store(dict(event,data={L:copies[key]}),sources[key],"person")=="keep"
            assert store(dict(event,data={L:copies[key]}),sources[key],"person")=="keep"
            assert len(sources[key].metadata["IngestConflicts"])==1
            assert sources[key].metadata["IngestConflicts"][0]["contact_ambiguous_sides"]==[L]
        assert len(events)==1 and events[0].data.first().saves==2
    assert final[0]==final[1]


def test_ingestion_attaches_to_existing_event_without_record():
    store,events,Event=ingestion_harness()
    old=Event(source=source("old","COMPLETED")); old.save()
    assert store({"date":100,"type":"PatientControllerEvent","name":"Synthetic","data":{L:side()}},source("new","COMPLETED"),"person")=="update"
    assert len(events[0].data.rows)==1
