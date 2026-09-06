"""Times represented by stored data, separate from import/job completion times.

Status polling reads database timestamps and compact existing settings caches.
It never decrypts raw neural exports, fetches Oura/REDCap, or creates caches.
"""
import datetime as dt
import hashlib
import math
import os
from pathlib import Path
import time

from Server import models
from modules import RCS08DataPolicy, RedcapStimulation, RedcapVisitContext, RedcapTimeline
from modules import RCS08OuraFreshness

ZONE = "America/Los_Angeles"


def unavailable(source, semantics, reason):
    return {"available": False, "value": None, "precision": None, "timezone": ZONE,
            "source": source, "semantics": semantics, "reason": reason, "partial": False}


def _valid_time(value, now):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 < value <= now)


def timestamp_entry(value, source, semantics, reason, *, now):
    entry = unavailable(source, semantics, reason)
    if _valid_time(value, now):
        entry.update(available=True, value=dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat(),
                     precision="second", reason=None)
    return entry


def reviewed_survey(participant, now):
    source = "Published corrected daily survey records and QC-valid testing-day context"
    semantics = "Latest reviewed survey represented in BRAVO; excluded raw surveys and upload times are not used."
    missing = unavailable(source, semantics, "No verified reviewed daily survey publication is available.")
    form = models.ScaleForms.find(institute=participant.institute, name="RCS08 Daily PRO (REDCap)",
                                  record_type="REDCap API Sync")
    if form is None:
        return missing
    try:
        RedcapTimeline.checked_fields(form, RedcapTimeline.DAILY_MAPPING, "reviewed_sha256")
    except RedcapTimeline.TimelineNotReady:
        return missing
    latest = models.ScaleRecord.objects.filter(participant=participant, source=form,
                                               date__gt=0, date__lte=now).order_by("-date").first()
    stamps = [] if latest is None else [latest.date]
    partial = False
    try:
        visit = RedcapVisitContext.read(form, now)
        partial = not visit["available"]
        stamps.extend(point["time"] for points in visit["metrics"].values() for point in points)
    except RedcapTimeline.TimelineNotReady:
        partial = True
    valid = [stamp for stamp in stamps if _valid_time(stamp, now)]
    entry = timestamp_entry(max(valid) if valid else None, source, semantics,
                            "No dated reviewed survey is represented in this publication.", now=now)
    if partial:
        entry.update(partial=True, reason="Testing-day publication is unavailable; this time covers reviewed routine surveys only.")
    return entry


def neural_sessions(participant, sources, now):
    """Native validated session boundaries, not decoder estimates or file dates."""
    reviewed = RCS08DataPolicy.applies_to(participant)
    policy_hash = hashlib.sha256(Path(RCS08DataPolicy.__file__).read_bytes()).hexdigest()
    stamps = []
    eligible = cached = dated = 0
    for source in sources:
        if (str(source.owner_id) != str(participant.uid) or source.type != "MedtronicJSON"
                or source.metadata.get("AnalysisExclusion") or not source.metadata.get("Device")):
            continue
        eligible += 1
        context, _ = RedcapStimulation.source_context(source, participant, reviewed, policy_hash, cached_only=True)
        if context is None:
            continue
        cached += 1
        if context["excluded"]:
            eligible -= 1
            cached -= 1
            continue
        values = [event["time"] for event in context["events"]
                  if event["kind"] == "settings_observed" and _valid_time(event["time"], now)
                  and (not reviewed or event["time"] >= RCS08DataPolicy.IMPLANT_DAY)]
        if values:
            dated += 1
            stamps.extend(values)
    entry = timestamp_entry(max(stamps) if stamps else None,
        "Validated native SessionDate / SessionEndDate in existing session-snapshot caches",
        "Latest represented active-group session snapshot; this is an observed session boundary, not a file-arrival time or the endpoint of continuous neural samples.",
        "No dated native session snapshot is available in the existing caches.", now=now)
    entry["coverage"] = {"eligible_sources": eligible, "cached_sources": cached, "dated_sources": dated}
    if dated < eligible:
        entry.update(partial=True, reason=f"{eligible - dated} eligible JSON exports have no available dated native snapshot; a later unindexed session may exist.")
    return entry


def for_institute(institute, *, now=None):
    """Return only the institute's RCS08 evidence; never create a participant."""
    now = time.time() if now is None else now
    result = {
        "redcap": unavailable("Reviewed daily survey publication", "Latest reviewed survey", "RCS08 is unavailable for this institute."),
        "neural_json": unavailable("Native JSON session snapshot", "Latest represented session time", "RCS08 is unavailable for this institute."),
        "neural_pdf": unavailable("PDF session report", "Time represented by a PDF report",
                                  "PDF session dates are not indexed by this integration."),
        "oura": RCS08OuraFreshness.unavailable("RCS08 is unavailable for this institute."),
    }
    owners = set(models.SourceFile.objects.filter(type="RCS08SurveyAudit", owner__institute=institute)
                 .values_list("owner_id", flat=True))
    named = models.Participant.find(name="RCS08", institute=institute)
    if named is not None:
        owners.add(named.uid)
    if len(owners) != 1:
        return result
    participant = models.Participant.find(uid=next(iter(owners)), institute=institute)
    if participant is None:
        return result
    result["redcap"] = reviewed_survey(participant, now)
    from modules import RCS08PDFMetadata
    result["neural_pdf"] = RCS08PDFMetadata.freshness(os.environ["DATASERVER_PATH"], participant.uid, now=now)
    sources = models.SourceFile.find_all(owner=participant, type="MedtronicJSON")
    result["neural_json"] = neural_sessions(participant, sources, now)
    result["oura"] = RCS08OuraFreshness.read_cached(participant, now)
    return result
