"""Explicit synthetic clinical inputs for tests; never an application fallback."""
import json


def install(monkeypatch, path, participant_uids):
    provenance = {"provenance": "Synthetic test evidence, not clinical guidance",
                  "evidence_ref": "synthetic-fixture", "source_commit": "a" * 40}
    timing = ("onset_upper_ms", "onset_lower_ms", "averaging_ms", "transition_up_ms",
              "transition_down_ms", "detection_blanking_ms", "adaptive_startup_delay_ms")
    record = {"safety_ceiling": dict(provenance, values_mA={"Left": 5.0, "Right": 5.0}),
              "timing": dict(provenance, fields={key: {"value_ms": 3000 if key == "averaging_ms" else 12000,
                                                       "why": "Synthetic timing", "confidence": "Low"}
                                               for key in timing}),
              "adaptive_eligibility": dict(provenance, programming_mode="parkinsons")}
    path.write_text(json.dumps({"schema_version": 1, "participants": {uid: record for uid in participant_uids}}))
    path.chmod(0o600)
    monkeypatch.setenv("BRAVO_CLINICAL_CONFIG_FILE", str(path))
