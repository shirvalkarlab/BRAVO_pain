# Preserve timestamps when de-identifying Percept imports

The original Dropbox reports remain read-only. BRAVO must store cleaned copies
of Percept reports for the reviewed participant whenever patient names, patient
IDs or birthdates have not already been redacted. A rebuild must never restore
unredacted patient-information fields from the original inputs.

`modules/PerceptPresentationPrivacy.py` removes direct patient identifiers from
Initial and Final patient-information states. It preserves session times, device
settings, recording samples and all other scientific content. The generic Percept
`deIdentification` helper randomizes timestamps and must not be used for this
longitudinal dataset.

The nightly/manual sync cleans the bytes before saving its source copy. The
reviewed participant's decoder also cleans stored bytes before processing browser
imports. The input's original keyed fingerprint remains the deduplication marker,
so re-reading an original Dropbox report does not produce a second import.

For an existing affected import, `deidentify_stored_source` writes and verifies a
new encrypted source copy, changes the source pointer and integrity hash in a
transaction, then removes the replaced stored bytes after commit. It does not
remove/recreate the source record or derived rows. Keep the original Dropbox file
as the recovery source. Do not publish original reports or private audit logs to Git.

Before accepting a repair or rebuilt database, verify:

- The stored source contains only blank/masked patient names and birthdates, plus
  the study ID where appropriate.
- Scientific report content outside the patient-information fields is identical.
- Derived recording and therapy counts/hashes are unchanged after a source-only repair.
- The original-file deduplication marker and original Dropbox bytes are unchanged.
- Running the cleaning step a second time makes no further changes.

The dated local audit identifies the affected original files privately. Shared
setup instructions do not need names, passwords or actual patient identifiers.
