# Private clinical configuration

Historical participant-specific clinical ceilings, timing recommendations, selected-band evidence and programming-mode observations are deployment inputs. They must not be embedded in application code or test fixtures. The module grid limit is not a substitute for a participant's clinical ceiling.

`BRAVO_CLINICAL_CONFIG_FILE` selects a JSON file outside the checkout and its published images. The application user must own this regular file; use owner-only permissions (`chmod 600`, or read-only `chmod 400`) and an owner-only parent directory. Set ownership to the actual application service user rather than assuming that a host account or root-owned mount is readable by the service. Symlinks, group/world-readable files, other-owner files and files above 2 MiB are rejected. No configuration is activated by default.

## Schema version 1

The root has `schema_version: 1` and `participants`, a mapping keyed by exact database participant UID. No wildcard, name-based matching or cross-participant fallback is supported. Every purpose section requires nonempty `provenance`, `evidence_ref` and a full 40-character `source_commit` identifying the reviewed source. These fields preserve provenance; their presence does not prove that a historical clinical decision remains applicable today.

| Section | Required contents |
| --- | --- |
| `safety_ceiling` | `values_mA`, mapping each required hemisphere to a finite positive number. A missing side is unavailable. A ceiling above the representable search-grid limit is conservatively clamped, with that change recorded. |
| `timing` | `fields` with exactly `onset_upper_ms`, `onset_lower_ms`, `averaging_ms`, `transition_up_ms`, `transition_down_ms`, `detection_blanking_ms`, `adaptive_startup_delay_ms`. Every field has `value_ms`, nonempty `why`, and `confidence` equal to `Low`, `Medium` or `High`. Values are finite nonnegative milliseconds; averaging is positive. Device constraints remain a separate validation gate. |
| `adaptive_eligibility` | `programming_mode`: `parkinsons` or `non_parkinsons`. This is an explicitly sourced programming-mode observation, not a diagnosis or permission to program a device. Actual decoded device facts take priority over historical observations. |
| `stage_gate_evidence` | `selected_bands` and `response_summary`, described below. This optional historical handover is never automatically substituted for live analysis. |

Each selected-band entry has `outcome`, `center_hz`, `band_width_hz`, `r`, `perm_p`, `fdr_q`, `exceeds_null_95th` and `provenance`. Frequency and width are positive finite numbers, correlation is in [-1, 1], probabilities are in [0, 1] or null, and the null-test verdict is boolean or null. Both outcome and provenance are nonempty strings.

A response summary has `responds` (boolean or null), `n_cells_suppressing` and `n_cells_total` (nonnegative integers or null), `one_sided_p` (probability or null), `replication_note` (string) and `source` (nonempty string). Suppressing-cell count cannot exceed the total. Unknown statistics remain null and never become a positive verdict.

## Fresh installation and invalidation

An archived configuration may use participant UIDs from a different database. Before enabling it, verify the corresponding identity against authorized source records and explicitly bind the reviewed configuration to the fresh installation's UID. Never infer this mapping from a label, automatically copy an old UID to a new participant, or apply one participant's evidence globally. Historical applicability and source identity need review independently of syntactic validation.

The loader exposes `ClinicalConfigurationUnavailable` for missing, unreadable or invalid evidence. Recommendation consumers must display an unavailable state, withhold programmable values, and avoid a generic/higher safety ceiling or timing default. Unrelated observational displays can remain available.

Saved-result signatures must include `config_digest()` and the exact participant identity. Timing result fields carry their exact `participant_uid` and `config_digest`; the digest is computed from the same bytes parsed into the section, so a concurrent file replacement cannot stamp old values with new evidence identity. The digest is derived from file contents, so changing evidence invalidates prior answers without editing code. Consumers must still validate required configuration before returning cached recommendations; a digest alone is not an eligibility check. Configuration remains private, including when the application repository is private.

Synthetic examples and validation cases live in `BRAVO/modules/DecodeCommon/tests/test_private_clinical_config.py`. They are unrelated to historical participant measurements.
