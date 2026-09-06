"""Remove direct patient identifiers without shifting scientific timestamps."""
import json
import re

FIELDS = frozenset({'PatientFirstName', 'PatientLastName', 'PatientId', 'PatientDateOfBirth'})


def sanitize_patient_identifiers(raw, study_id='RCS08'):
    report = json.loads(raw)
    if not isinstance(report, dict):
        raise ValueError('Percept report must be an object')
    information = report.get('PatientInformation', {})
    if not isinstance(information, dict):
        raise ValueError('PatientInformation must be an object')
    changed = []
    for state, entry in information.items():
        if not isinstance(entry, dict):
            raise ValueError('Percept patient-information state must be an object')
        for field in FIELDS.intersection(entry):
            value = entry[field]
            if isinstance(value, (dict, list)):
                raise ValueError('Unexpected structured patient identifier')
            # Keep existing blank/block-character redaction as-is.
            if value is None or value == 0 or not re.search(r'[A-Za-z0-9]', str(value)):
                continue
            replacement = study_id if field == 'PatientId' else ''
            if value != replacement:
                entry[field] = replacement
                changed.append(f'PatientInformation.{state}.{field}')
    if not changed:
        return raw, []
    return json.dumps(report, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), sorted(changed)


def deidentify_stored_source(source, study_id='RCS08'):
    """Atomically replace only encrypted source bytes; retain derived rows and dedup ID."""
    from pathlib import Path
    from uuid import uuid4
    from django.db import transaction
    from modules import DataCurator, Database

    raw = DataCurator.loadCacheFile(source)
    cleaned, fields = sanitize_patient_identifiers(raw, study_id)
    if not fields:
        return cleaned, []
    old_pointer = source.pointer
    new_pointer = str(Path(old_pointer).with_name(source.uid + '-' + uuid4().hex + '.deidentified.json'))
    hashed = Database.saveSourceFile(DataCurator.secureEncoder.encrypt(cleaned), new_pointer, bytes=True)
    if not hashed:
        raise ValueError('Deidentified source could not be written')
    verified = DataCurator.secureEncoder.decrypt(Database.loadSourceFile(new_pointer, hashed, bytes=True))
    if verified != cleaned:
        raise ValueError('Deidentified source verification failed')
    metadata = dict(source.metadata)
    metadata['DirectIdentifierPolicy'] = 1
    metadata['DirectIdentifierFieldsRemoved'] = fields
    with transaction.atomic():
        source.pointer = new_pointer
        source.hashed = hashed
        source.metadata = metadata
        # UniqueHashed remains the original input fingerprint: repeated raw imports
        # must be recognized as duplicates even though the retained copy is cleaned.
        source.save(update_fields=['pointer', 'hashed', 'metadata'])
        transaction.on_commit(lambda: Database.deleteSourceFile(old_pointer))
    return cleaned, fields
