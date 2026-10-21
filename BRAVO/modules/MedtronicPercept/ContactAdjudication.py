"""Validated, reversible reviewed contacts alongside unchanged device-source claims.

This is not an automatic temporal fallback. A private review must bind an explicit
decision to one recording, hemisphere, native identity and exact stored spectrum.
The source conflict remains available even when that decision is used in analysis.
"""
from datetime import datetime
import re

VERSION = "event-contact-adjudication-v1"
METHOD = "operator_confirmed_sensing_change_with_device_timeline"
STATUS = "timeline_adjudicated"
SUMMARY = "Assigned from sensing-change timeline; conflicting export labels retained."
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CONTACTS = {"SensingElectrodeConfigDef." + pair for pair in (
    "ZERO_AND_ONE", "ZERO_AND_TWO", "ZERO_AND_THREE", "ONE_AND_TWO",
    "ONE_AND_THREE", "TWO_AND_THREE",
)}


def _claims(block):
    """Compare claim values, not copy counts: repeat imports are not new evidence."""
    values = set()
    observations = block.get("SenseIDObservations")
    if not isinstance(observations, list) or not observations:
        return None
    for item in observations:
        if not isinstance(item, dict):
            return None
        value = item.get("sense_id")
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or value.split(".")[-1].upper() == "NOT_SET":
            continue
        values.add(value)
    return sorted(values)


def validated_contact_adjudication(block, *, hemisphere, recording_uid):
    """Return only safe presentation fields, or None when any binding is invalid.

Raw identity is established at ingestion/review with the original source, never
inferred from rounded database numbers. The separate stored digest detects any
subsequent array change without pretending SQL numbers are original raw values.
"""
    from .BrainSenseEvent import RAW_SPECTRUM_VERSION, rawSpectrumDigest

    if not isinstance(block, dict) or not recording_uid:
        return None
    review, identity = block.get("ContactAdjudication"), block.get("RawSpectrumIdentity")
    if not isinstance(review, dict) or not isinstance(identity, dict):
        return None
    if (review.get("version") != VERSION or review.get("status") != STATUS
            or review.get("method") != METHOD
            or str(review.get("recording_uid", "")) != str(recording_uid)
            or hemisphere not in ("HemisphereLocationDef.Left", "HemisphereLocationDef.Right")
            or review.get("hemisphere") != hemisphere
            or review.get("sense_id") not in _CONTACTS):
        return None
    if (identity.get("version") != RAW_SPECTRUM_VERSION
            or not identity.get("source_id") or not identity.get("source_hash")
            or block.get("UnverifiedSenseIDObservations")
            or block.get("SpectrumIdentityStatus") == "unverified"):
        return None
    for key in ("raw_identity_sha256", "raw_spectrum_sha256", "stored_spectrum_sha256", "evidence_sha256"):
        if not isinstance(review.get(key), str) or not _HASH.fullmatch(review[key]):
            return None
    if (review["raw_identity_sha256"] != identity.get("raw_identity_sha256")
            or review["raw_spectrum_sha256"] != identity.get("sha256")):
        return None
    native_clock = {key: block.get(key) for key in
                    ("DateTimeBlockId", "DateTimeOffsetInSeconds", "GroupId")}
    if any(value is None for value in native_clock.values()) or review.get("native_clock") != native_clock:
        return None
    claims = _claims(block)
    if (claims is None or review.get("source_claims") != claims
            or review["sense_id"] not in claims):
        return None
    try:
        reviewed = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
        if reviewed.tzinfo is None or rawSpectrumDigest(block) != review["stored_spectrum_sha256"]:
            return None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return {"sense_id": review["sense_id"], "status": STATUS, "summary": SUMMARY,
            "source_conflict": bool(block.get("SenseIDConflict") or block.get("SenseIDStatus") == "ambiguous")}
