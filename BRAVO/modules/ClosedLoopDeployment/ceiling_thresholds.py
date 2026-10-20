"""Participant-bound historical spike ceilings, supplied privately at deployment.

Set BRAVO_POWER_CEILING_CONFIG_DIR to a private directory. Each JSON filename is
SHA256(participant UID) + '.json'; its participant_uid must match the requested
UID exactly. Schema 1 contains percentile (99.5), nonempty provenance, and tables
of {electrode, centre_hz, ceiling} entries for POWER_DOMAIN_CEILINGS (required),
TIME_DOMAIN_CEILINGS and RAW_LSB_CEILINGS (optional, currently not consumed).

Ceilings are empirical participant data, never device constants. Missing or
invalid configuration makes ceiling-qualified analysis unavailable; a matching
validated table may omit a pair with no historical basis, preserving the source
rule of applying no ceiling to that pair. Raw recordings are never changed.
The content digest belongs in every derived-result cache identity.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path

PERCENTILE = 99.5
SCHEMA_VERSION = 1
_TABLES = ('POWER_DOMAIN_CEILINGS', 'TIME_DOMAIN_CEILINGS', 'RAW_LSB_CEILINGS')


@dataclass(frozen=True)
class CeilingConfiguration:
    participant_uid: str
    status: str
    digest: str = ''
    tables: dict = field(default_factory=dict)

    @property
    def available(self):
        return self.status == 'available'

    @property
    def reason(self):
        return '' if self.available else 'Participant-specific historical power ceiling configuration is unavailable (' + self.status + ').'

    def power_ceiling(self, sensing_contact, centre_hz):
        if not self.available or sensing_contact is None or centre_hz is None:
            return None
        try:
            centre = float(centre_hz)
        except (ValueError, TypeError):
            return None
        if not math.isfinite(centre):
            return None
        return self.tables['POWER_DOMAIN_CEILINGS'].get((str(sensing_contact), round(centre, 1)))


def _validate_tables(document):
    if (type(document.get('schema_version')) is not int
            or document['schema_version'] != SCHEMA_VERSION or document.get('percentile') != PERCENTILE):
        raise ValueError('unsupported schema or percentile')
    provenance = document.get('provenance')
    if not isinstance(provenance, dict) or not all(
            isinstance(provenance.get(k), str) and provenance[k].strip()
            for k in ('source_sha', 'computed_at', 'method')):
        raise ValueError('missing provenance')
    raw = document.get('tables')
    if not isinstance(raw, dict) or 'POWER_DOMAIN_CEILINGS' not in raw or set(raw) - set(_TABLES):
        raise ValueError('invalid tables')
    tables = {}
    for name, rows in raw.items():
        if not isinstance(rows, list):
            raise ValueError('table must contain entries')
        table = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('electrode'), str) or not row['electrode'].strip():
                raise ValueError('invalid electrode')
            centre, ceiling = row.get('centre_hz'), row.get('ceiling')
            if (type(centre) not in (int, float) or type(ceiling) not in (int, float)
                    or not math.isfinite(centre) or not math.isfinite(ceiling)
                    or centre < 0 or ceiling <= 0):
                raise ValueError('invalid centre or ceiling')
            key = (row['electrode'], round(float(centre), 1))
            if key in table:
                raise ValueError('duplicate electrode and centre')
            table[key] = float(ceiling)
        tables[name] = table
    return tables


def load_configuration(participant_uid):
    """Read once per computation; never reuse another participant's configuration."""
    uid = str(participant_uid) if participant_uid is not None else ''
    if not uid:
        return CeilingConfiguration(uid, 'missing_participant')
    root = os.environ.get('BRAVO_POWER_CEILING_CONFIG_DIR')
    if not root:
        return CeilingConfiguration(uid, 'not_configured')
    path = Path(root) / (hashlib.sha256(uid.encode('utf-8')).hexdigest() + '.json')
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return CeilingConfiguration(uid, 'missing')
    except OSError:
        return CeilingConfiguration(uid, 'unreadable')
    digest = hashlib.sha256(content).hexdigest()
    try:
        document = json.loads(content)
        if not isinstance(document, dict):
            raise ValueError('document must be an object')
        if document.get('participant_uid') != uid:
            return CeilingConfiguration(uid, 'participant_mismatch', digest)
        tables = _validate_tables(document)
    except (ValueError, TypeError, UnicodeError):
        return CeilingConfiguration(uid, 'invalid', digest)
    return CeilingConfiguration(uid, 'available', digest, tables)


def configuration_identity(participant_uid):
    config = load_configuration(participant_uid)
    return (SCHEMA_VERSION, config.status, config.digest)
