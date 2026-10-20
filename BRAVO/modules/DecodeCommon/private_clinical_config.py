"""Participant-bound clinical inputs, supplied privately by the deployment owner.

Set BRAVO_CLINICAL_CONFIG_FILE to an owner-only JSON file outside the repository.
The version-1 document contains ``participants[uid][section]``; every section must
state its source commit, evidence reference and provenance. This is historical
provenance, not proof that a clinical decision remains applicable today.
Missing or malformed configuration never supplies a clinical default. Callers
must turn ClinicalConfigurationUnavailable into an explicit unavailable result.
Use config_digest in saved-result keys because configuration is outside code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys

# Both host and Django import spellings must share the same exception class.
_other_name = __name__.removeprefix("modules.") if __name__.startswith("modules.") else "modules." + __name__
sys.modules.setdefault(_other_name, sys.modules[__name__])

ENVIRONMENT_VARIABLE = "BRAVO_CLINICAL_CONFIG_FILE"
_MAX_BYTES = 2 * 1024 * 1024


class ClinicalConfigurationUnavailable(ValueError):
    """A recommendation cannot be made from the configured clinical evidence."""


def _read_bytes():
    path = os.environ.get(ENVIRONMENT_VARIABLE)
    if not path:
        raise ClinicalConfigurationUnavailable("Private clinical configuration is not configured.")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                    or info.st_uid != os.geteuid() or info.st_size > _MAX_BYTES):
                raise ClinicalConfigurationUnavailable(
                    "Clinical configuration must be an owner-only regular file within the size limit.")
            raw = stream.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise ClinicalConfigurationUnavailable("Clinical configuration exceeds the size limit.")
            return raw
    except OSError as exc:
        raise ClinicalConfigurationUnavailable("Private clinical configuration cannot be read.") from exc


def config_digest():
    """Content identity for all result caches; do not expose the private path."""
    try:
        return hashlib.sha256(_read_bytes()).hexdigest()
    except ClinicalConfigurationUnavailable:
        return "clinical-config-unavailable-v1"


def participant_section(participant_uid, section):
    """Return one explicitly bound section; no wildcard or other-participant fallback."""
    if participant_uid is None or not str(participant_uid).strip():
        raise ClinicalConfigurationUnavailable("A participant identity is required for clinical configuration.")
    raw = _read_bytes()
    try:
        document = json.loads(raw, object_pairs_hook=_unique_keys)
    except (ValueError, UnicodeError) as exc:
        raise ClinicalConfigurationUnavailable("Private clinical configuration is invalid JSON.") from exc
    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1):
        raise ClinicalConfigurationUnavailable("Unsupported clinical configuration schema.")
    participants = document.get("participants")
    participant = participants.get(str(participant_uid)) if isinstance(participants, dict) else None
    record = participant.get(section) if isinstance(participant, dict) else None
    if not isinstance(record, dict):
        raise ClinicalConfigurationUnavailable("No clinical configuration exists for this participant and purpose.")
    if any(not isinstance(record.get(key), str) or not record[key].strip()
           for key in ("provenance", "evidence_ref", "source_commit")):
        raise ClinicalConfigurationUnavailable("Clinical configuration is missing source provenance.")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", record["source_commit"]):
        raise ClinicalConfigurationUnavailable("Clinical configuration has an invalid source commit.")
    return dict(record, configuration_digest=hashlib.sha256(raw).hexdigest())


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate clinical configuration key.")
        result[key] = value
    return result


def adaptive_eligibility_for(participant_uid):
    """An explicit historical programming-mode fact, never an inferred diagnosis."""
    record = participant_section(participant_uid, "adaptive_eligibility")
    if record.get("programming_mode") not in ("parkinsons", "non_parkinsons"):
        raise ClinicalConfigurationUnavailable("No verified programming mode is configured for this participant.")
    return record


def stage_gate_evidence_for(participant_uid):
    """Validate optional historical handover evidence; live analyses take priority."""
    import math
    record = participant_section(participant_uid, "stage_gate_evidence")
    bands, response = record.get("selected_bands"), record.get("response_summary")
    if not isinstance(bands, list) or not bands or not isinstance(response, dict):
        raise ClinicalConfigurationUnavailable("Historical gate evidence is incomplete.")
    def number(value, low, high, optional=False):
        if value is None and optional:
            return
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ClinicalConfigurationUnavailable("Historical gate evidence has an invalid numeric value.")
    band_fields = {"outcome", "center_hz", "band_width_hz", "r", "perm_p", "fdr_q",
                   "exceeds_null_95th", "provenance"}
    for band in bands:
        if not isinstance(band, dict) or set(band) != band_fields:
            raise ClinicalConfigurationUnavailable("Historical selected-band evidence is incomplete.")
        if any(not isinstance(band[key], str) or not band[key].strip()
               for key in ("outcome", "provenance")):
            raise ClinicalConfigurationUnavailable("Selected-band evidence requires its outcome and provenance.")
        number(band["center_hz"], 0, float("inf"))
        number(band["band_width_hz"], 0, float("inf"))
        if band["center_hz"] == 0 or band["band_width_hz"] == 0:
            raise ClinicalConfigurationUnavailable("Selected-band frequency and width must be positive.")
        number(band["r"], -1, 1)
        for key in ("perm_p", "fdr_q"):
            number(band[key], 0, 1, optional=True)
        if band["exceeds_null_95th"] is not None and type(band["exceeds_null_95th"]) is not bool:
            raise ClinicalConfigurationUnavailable("Selected-band evidence has an invalid null-test verdict.")
    response_fields = {"responds", "n_cells_suppressing", "n_cells_total", "one_sided_p", "replication_note", "source"}
    if set(response) != response_fields:
        raise ClinicalConfigurationUnavailable("Historical response evidence is incomplete.")
    if response["responds"] is not None and type(response["responds"]) is not bool:
        raise ClinicalConfigurationUnavailable("Historical response evidence has an invalid verdict.")
    counts = [response[key] for key in ("n_cells_suppressing", "n_cells_total")]
    if any(value is not None and (type(value) is not int or value < 0) for value in counts):
        raise ClinicalConfigurationUnavailable("Historical response counts must be nonnegative integers.")
    if all(value is not None for value in counts) and counts[0] > counts[1]:
        raise ClinicalConfigurationUnavailable("Historical response counts are inconsistent.")
    number(response["one_sided_p"], 0, 1, optional=True)
    if (not isinstance(response["source"], str) or not response["source"].strip()
            or not isinstance(response["replication_note"], str)):
        raise ClinicalConfigurationUnavailable("Historical response evidence requires source attribution.")
    return record
