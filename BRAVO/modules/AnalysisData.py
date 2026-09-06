"""Approved inputs shared by Aditya reports and imported research analyses.

Stored ScaleRecords already contain the reviewed exclusions and timestamp/value
corrections. Never pull REDCap or re-score those rows here. Historical forms stay
separate from daily PROs, even when their metric labels look similar.
"""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
from Server import models

VERSION = "aditya-canonical-inputs-1"
PRASAD_SOURCE = "d745360d898647048213c561d18e30e3064ad8e7"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def eligible_source_files(participant):
    """Analysis excludes quarantined originals; raw source inspection retains them."""
    sources = models.SourceFile.find_all(owner=participant)
    excluded = [source.uid for source in sources
                if (source.metadata or {}).get("AnalysisExclusion")]
    return sources.exclude(uid__in=excluded)


def canonical_pros(participant):
    from modules.RCS08Sync import REDCAP_FORM_NAME, REDCAP_RECORD_TYPE
    from modules.RCS08DataPolicy import applies_to
    if not applies_to(participant):
        return pd.DataFrame()
    form = models.ScaleForms.find(institute=participant.institute, name=REDCAP_FORM_NAME,
                                 record_type=REDCAP_RECORD_TYPE)
    if form is None:
        return pd.DataFrame()
    if not isinstance(form.record, list) or not form.record:
        raise ValueError("The managed daily survey has no approved field mapping")
    processing = form.record[0].get("processing", {})
    if not re.fullmatch(r"[0-9a-f]{64}", str(processing.get("reviewed_sha256", ""))):
        raise ValueError("The daily survey is missing its reviewed QC provenance")
    fields = [(page_i, question_i, question)
              for page_i, page in enumerate(form.record)
              for question_i, question in enumerate(page.get("questions", []))
              if question.get("type") == "score"]
    keys = [question.get("variableName") for _, _, question in fields]
    reserved = {"record_uid", "source_record", "source_form_uid", "source_form", "date_time_s1_daily"}
    if (not keys or any(not isinstance(key, str) or not key.strip() or key.startswith("_")
                        or key in reserved for key in keys) or len(set(keys)) != len(keys)):
        raise ValueError("The managed survey has invalid or duplicate metric identifiers")
    records = models.ScaleRecord.find_all(source=form, participant=participant).order_by("date", "name")
    rows = []
    for record in records:
        if (not isinstance(record.record, list) or len(record.record) != len(form.record)
            or any(not isinstance(values, list) or len(values) != len(page.get("questions", []))
                   for values, page in zip(record.record, form.record))):
            raise ValueError("A managed survey row does not match its approved field mapping")
        row = {"record_uid": record.uid, "source_record": record.name,
               "source_form_uid": form.uid, "source_form": form.name,
               "_pro_time_utc": pd.to_datetime(record.date, unit="s", utc=True).tz_localize(None),
               "date_time_s1_daily": pd.to_datetime(record.date, unit="s", utc=True)}
        for page_i, question_i, question in fields:
            try:
                value = record.record[page_i][question_i]
            except (IndexError, TypeError):
                raise ValueError("A managed survey row does not match its approved field mapping")
            row[question["variableName"]] = pd.to_numeric(value, errors="coerce")
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.attrs["metrics"] = [{"key": q["variableName"], "label": q["text"],
                               "range": [q.get("min"), q.get("max")]}
                              for _, _, q in fields]
    frame.attrs["processing"] = processing
    return frame


def input_manifest(participant):
    """Content fingerprints exclude recomputable caches and include approved data/QC.

    Keeping source identity distinct from algorithm identity permits different
    analyses on the same approved observations without calling their outputs raw.
    """
    from modules import RCS08DataPolicy, ReportCache
    from modules.OURA.QualityControl import VERSION as OURA_VERSION, POLICY_PATH
    source_rows = []
    excluded = []
    cache_types = {"CachedResult", "ChronicNeuralActivitySource", "ProcessedCustomizedStreamingData"}
    for source in models.SourceFile.find_all(owner=participant).order_by("uid"):
        if source.type in cache_types:
            continue
        entry = [source.uid, source.type, source.hashed, source.metadata]
        (excluded if (source.metadata or {}).get("AnalysisExclusion") else source_rows).append(entry)
    surveys = list(models.ScaleRecord.find_all(participant=participant).order_by("source_id", "date", "name")
                   .values_list("uid", "source_id", "date", "name", "record"))
    form_ids = {row[1] for row in surveys}
    forms = list(models.ScaleForms.objects.filter(uid__in=form_ids).order_by("uid")
                 .values_list("uid", "record_type", "record"))
    source_ids = [row[0] for row in source_rows]
    recordings = list(models.Recording.objects.filter(source_id__in=source_ids, original__isnull=True)
                      .exclude(type__startswith="Processed").order_by("uid")
                      .values_list("uid", "source_id", "type", "date", "hashed", "metadata",
                                   "adjusted_alignment", "fs_scaling_factor"))
    policy_hashes = {}
    for path in (Path(RCS08DataPolicy.__file__), Path(POLICY_PATH),
                 Path(__file__).parent / "OURA/QualityControl.py"):
        policy_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    model_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((Path(__file__).parent / "Biomarkers/data/psd_lsb_models").glob("*.json"))}
    result = {
        "version": VERSION, "participant_uid": participant.uid,
        "data_revision": ReportCache.revision(),
        "source_fingerprint": _digest(source_rows), "source_count": len(source_rows),
        "excluded_sources": [row[0] for row in excluded],
        "survey_fingerprint": _digest([forms, surveys]), "survey_rows": len(surveys),
        "recording_fingerprint": _digest(recordings), "recordings": len(recordings),
        "policy_hashes": policy_hashes, "oura_qc_version": OURA_VERSION,
        "model_hashes": model_hashes,
        "prasad_source_commit": PRASAD_SOURCE,
        "daily_pro_scope": "Approved daily PRO records; historical forms remain separate",
    }
    result["fingerprint"] = _digest(result)
    return result
