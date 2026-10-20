""""""
"""
=========================================================
* UF BRAVO Platform  (Pain fork)
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Django persistence for offline REDCap CSV / DataFrame ingest.
=============================================================

`RedcapImport` (pure pandas) turns a tidy REDCap export into FieldMapping + record dicts. This
module writes those into the platform's NATIVE tables so the imported PROs render and analyse with
no frontend change:

    ScaleForms (record_type="Redcap CSV Import")   -- the form; `record` holds the FieldMapping
                                                      list (same shape Normal surveys use, so
                                                      get_info() returns it directly to the UI).
    ParticipantLinkRel                              -- links the form to the participant. REQUIRED:
                                                      DataAnalysis.getChronicTimeline iterates the
                                                      participant's links to build the
                                                      CustomizedSurveyData outcome channels.
    ScaleRecord (one per report)                    -- record = the Result matrix; date = report ts.

Re-import is IDEMPOTENT: importing the same instrument for the same participant deletes that
participant's prior ScaleRecords for the form and rewrites them, and refreshes the form's
FieldMapping (bumping record_version) if it changed.
"""

import json
import hashlib

from Server import models
from . import RedcapImport


def _records_fingerprint(records):
    """Stable content hash of a list of {Date, Result} records (order-independent).

    Used to decide whether a re-import would actually change anything: if the parsed export
    fingerprints identically to what is already stored for this (participant, form), the import is
    skipped (no redundant deletes / version churn). When the upstream REDCap export changes (new
    daily reports fetched), the fingerprint differs and the records are rewritten.
    """
    items = []
    for r in records:
        # round the epoch to whole seconds so float repr jitter doesn't spuriously differ
        try:
            date_key = round(float(r.get("Date")), 0)
        except (TypeError, ValueError):
            date_key = r.get("Date")
        items.append((date_key, json.dumps(r.get("Result"), sort_keys=True, default=str)))
    items.sort(key=lambda x: (x[0] is None, x[0], x[1]))
    blob = json.dumps(items, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _stored_fingerprint(form, participant):
    """Fingerprint of the records CURRENTLY stored for (participant, form), in the same shape."""
    stored = models.ScaleRecord.objects.filter(source=form, participant=participant)
    records = [{"Date": s.date, "Result": s.record} for s in stored]
    return _records_fingerprint(records)


def _get_or_create_form(institute, name, field_mapping):
    """Find the (institute, name) form of our record_type, or create it. Returns the ScaleForms.

    If the form exists with a different FieldMapping, its version is bumped via update_version
    (which itself decides in-place vs new-version depending on whether records already reference it).
    """
    form = models.ScaleForms.find(institute=institute, name=name, record_type=RedcapImport.RECORD_TYPE)
    if form is None:
        form = models.ScaleForms.create(institute, name, RedcapImport.RECORD_TYPE)
        form.record = field_mapping
        form.save()
        return form

    # Existing form: refresh FieldMapping if it changed (update_version is a no-op when equal).
    if json.dumps(form.record) != json.dumps(field_mapping):
        form = form.update_version(field_mapping)
    return form


def _ensure_link(participant, form):
    """Ensure a ParticipantLinkRel exists for (participant, form). Returns the link."""
    link = models.ParticipantLinkRel.find(participant=participant, record=form)
    if link is None:
        link = models.ParticipantLinkRel.create(participant, form)
    return link


def persist_instrument(participant, institute, parsed, form_name=None, replace=True,
                       skip_if_unchanged=False):
    """Persist ONE parsed instrument (output of RedcapImport.build_instrument) for a participant.

    Parameters
    ----------
    participant : Server.models.Participant
    institute   : Server.models.Institute  (the form owner / permission scope)
    parsed      : dict  -- {"FieldMapping": [...], "records": [...], "metrics": [...], ...}
    form_name   : str | None  -- overrides the instrument header as the form name.
    replace     : bool  -- if True, delete this participant's existing ScaleRecords for the form
                  before inserting (idempotent re-import). If False, append.

    Returns
    -------
    dict  -- {"FormId", "FormName", "Version", "RecordType", "RecordsImported", "Metrics",
              "Fields", "Skipped"}.
    """
    field_mapping = parsed["FieldMapping"]
    name = form_name or field_mapping[0].get("header") or "Imported REDCap Survey"

    fields = [q["text"] for q in field_mapping[0]["questions"] if q.get("type") in ("score", "redcapForm", "cumulativeScore") and q.get("text") != "Time"]

    # Content-aware short-circuit (used by silent auto-import): if a form with this name already
    # holds records that fingerprint identically to the parsed export, do nothing. This makes
    # auto-import-on-load free to call on every page visit, and a re-import happens ONLY when the
    # upstream export actually changed (new REDCap reports).
    if skip_if_unchanged:
        existing = models.ScaleForms.find(institute=institute, name=name,
                                          record_type=RedcapImport.RECORD_TYPE)
        if existing is not None:
            new_fp = _records_fingerprint(parsed["records"])
            if _stored_fingerprint(existing, participant) == new_fp:
                _ensure_link(participant, existing)  # ensure the link exists even on a no-op
                return {
                    "FormId": existing.uid,
                    "FormName": existing.name,
                    "Version": existing.record_version,
                    "RecordType": existing.record_type,
                    "RecordsImported": models.ScaleRecord.objects.filter(source=existing, participant=participant).count(),
                    "Metrics": parsed.get("metrics", []),
                    "Fields": fields,
                    "Skipped": parsed.get("skipped", 0),
                    "Unchanged": True,
                }

    form = _get_or_create_form(institute, name, field_mapping)
    _ensure_link(participant, form)

    if replace:
        models.ScaleRecord.objects.filter(source=form, participant=participant).delete()

    imported = 0
    for rec in parsed["records"]:
        models.ScaleRecord.create(participant, form, rec["Result"], date=rec["Date"])
        imported += 1

    return {
        "FormId": form.uid,
        "FormName": form.name,
        "Version": form.record_version,
        "RecordType": form.record_type,
        "RecordsImported": imported,
        "Metrics": parsed.get("metrics", []),
        "Fields": fields,
        "Skipped": parsed.get("skipped", 0),
        "Unchanged": False,
    }


def import_export(participant, institute, source, instrument_name=None, layout="auto",
                  replace=True, skip_if_unchanged=False, **kwargs):
    """Parse a CSV path / DataFrame and persist every instrument it contains for a participant.

    `skip_if_unchanged=True` makes each instrument a no-op when its parsed records already match
    what is stored (used by silent auto-import). Returns a list of per-instrument result dicts.
    """
    parsed_list = RedcapImport.parse_export(source, instrument_name=instrument_name,
                                            layout=layout, **kwargs)
    results = []
    for parsed in parsed_list:
        if not parsed["records"]:
            continue
        results.append(persist_instrument(participant, institute, parsed,
                                          form_name=instrument_name if len(parsed_list) == 1 else None,
                                          replace=replace, skip_if_unchanged=skip_if_unchanged))
    return results
