"""Opt-in identity scope and rooted receipts for serial-masked Percept reports.

This is continuity-based admission to one already verified implant, not recovery
of a serial number. Incoming reports never select the owner, institute or device.
No database, provider, filesystem or application imports belong in this module.
"""
import hashlib
import hmac
import json
import math
from datetime import datetime

try:
    from . import state, native_continuity
except ImportError:
    import state
    import native_continuity

POLICY_VERSION = 'masked-native-continuity-v1'
BINDING_FIELDS = {'policy', 'scope', 'participant_uid', 'institute_uid',
                  'device_uid', 'seed_source_uid', 'seed_raw_sha256'}
RECORD_FIELDS = {'policy', 'binding_sha256', 'source_uid', 'raw_sha256',
                 'reference_source_uid', 'reference_raw_sha256', 'continuity',
                 'clock', 'admission_hmac_sha256'}
SIGNING_DOMAIN = b'BRAVO/masked-native-admission/v1\0'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def binding(config):
    """Validate a private opt-in; an absent opt-in preserves the strict old gate."""
    value = config['upstream'].get('masked_device_binding')
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != BINDING_FIELDS:
        raise ValueError('masked device binding fields invalid')
    if (value['policy'] != POLICY_VERSION or value['scope'] != config['upstream']['scope']
            or value['participant_uid'] != config['target_participant_uid']
            or value['institute_uid'] != config['target_institute_uid']):
        raise ValueError('masked device binding scope invalid')
    for field in ('participant_uid', 'institute_uid', 'device_uid', 'seed_source_uid'):
        state.uid(value[field])
    state.digest(value['seed_raw_sha256'])
    return dict(value)


def masked_serial(report):
    """Only matching wholly block-masked Initial/Final serials are supported."""
    try:
        first, last = (report['DeviceInformation'][phase]['NeurostimulatorSerialNumber']
                       for phase in ('Initial', 'Final'))
    except (KeyError, TypeError):
        raise ValueError('masked report serial fields unavailable') from None
    if (not isinstance(first, str) or not first or first != last
            or not all(0x2580 <= ord(c) <= 0x259f for c in first)):
        raise ValueError('masked report serials invalid or disagree')
    return first


def advancing_session(candidate, reference):
    """The opt-in covers new reads in one native block, never replayed old reads."""
    def bounds(report):
        if any(not isinstance(report[key], str) for key in ('SessionDate', 'SessionEndDate')):
            raise ValueError('masked session dates unavailable')
        dates = [datetime.fromisoformat(report[key].replace('Z', '+00:00'))
                 for key in ('SessionDate', 'SessionEndDate')]
        first, last = (report['DeviceInformation'][phase] for phase in ('Initial', 'Final'))
        offsets = [node['DeviceDateTimeOffsetInSeconds'] for node in (first, last)]
        def valid_offset(value):
            try:
                return type(value) in (int, float) and math.isfinite(value) and value >= 0
            except OverflowError:
                return False
        if (any(date.tzinfo is None for date in dates) or dates[0] > dates[1]
                or any(type(node['DeviceDateTimeBlockId']) is not int or node['DeviceDateTimeBlockId'] < 0 for node in (first, last))
                or first['DeviceDateTimeBlockId'] != last['DeviceDateTimeBlockId']
                or any(not valid_offset(value) for value in offsets)
                or offsets[0] > offsets[1]):
            raise ValueError('masked session bounds invalid')
        return first['DeviceDateTimeBlockId'], offsets[1], dates[0], dates[1]
    old, new = bounds(reference), bounds(candidate)
    if old[0] != new[0] or old[1] >= new[1] or old[2] >= new[2] or old[3] >= new[3]:
        raise ValueError('masked session does not advance the trusted read')


def validate_key(key):
    if not isinstance(key, bytes) or not key:
        raise ValueError('masked certificate signing key unavailable')


def _signature(value, key):
    validate_key(key)
    payload = {name: item for name, item in value.items() if name != 'admission_hmac_sha256'}
    return hmac.new(key, SIGNING_DOMAIN + json.dumps(payload, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode(), hashlib.sha256).hexdigest()


def record(scope, source_uid, raw_sha, reference_uid, reference_sha, continuity, clock, key):
    """Persist only compact evidence, bound to the exact source and private opt-in."""
    value = {'policy': POLICY_VERSION, 'binding_sha256': digest(scope),
            'source_uid': state.uid(source_uid), 'raw_sha256': state.digest(raw_sha),
            'reference_source_uid': state.uid(reference_uid),
            'reference_raw_sha256': state.digest(reference_sha),
            'continuity': continuity, 'clock': clock}
    value['admission_hmac_sha256'] = _signature(value, key)
    return value


def trusted_references(scope, rows, key):
    """Root a rolling reference set at the exact reviewed source, never date alone.

    Rows are already owner/implant-scoped projections from the trusted runtime.
    A stored descendant certificate supplies a directed edge to a previously
    trusted original source. Cycles, unrelated rows and altered receipts cannot
    establish trust. The runtime separately authenticates every selected raw.
    """
    validate_key(key)
    rows = list(rows)
    by = {(row['source_uid'], row['raw_sha256']): row for row in rows}
    if len(by) != len(rows):
        raise ValueError('masked reference identity ambiguous')
    seed = (scope['seed_source_uid'], scope['seed_raw_sha256'])
    if seed not in by:
        raise ValueError('masked reference seed unavailable')
    expected = digest(scope)
    trusted = {seed}
    while True:
        additions = set()
        for identity, row in by.items():
            receipt = row.get('admission')
            if identity in trusted or not isinstance(receipt, dict) or set(receipt) != RECORD_FIELDS:
                continue
            if (receipt['policy'] != POLICY_VERSION or receipt['binding_sha256'] != expected
                    or (receipt['source_uid'], receipt['raw_sha256']) != identity
                    or not isinstance(receipt['continuity'], dict) or not receipt['continuity']
                    or not isinstance(receipt['clock'], dict) or not receipt['clock']):
                continue
            try:
                native_continuity.validate_receipt(receipt['continuity'])
                clock = receipt['clock']
                if set(clock) != {'agreement', 'table_digest', 'configuration_digest'}:
                    continue
                state.digest(clock['configuration_digest'])
                if (not isinstance(clock['table_digest'], str) or len(clock['table_digest']) != 16
                        or any(c not in '0123456789abcdef' for c in clock['table_digest'])):
                    continue
                native_continuity.validate_clock_receipt(clock['agreement'])
                for field in ('source_uid', 'reference_source_uid'):
                    state.uid(receipt[field])
                for field in ('raw_sha256', 'reference_raw_sha256', 'admission_hmac_sha256'):
                    state.digest(receipt[field])
                if not hmac.compare_digest(_signature(receipt, key), receipt['admission_hmac_sha256']):
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            if (receipt['reference_source_uid'], receipt['reference_raw_sha256']) in trusted:
                additions.add(identity)
        if not additions:
            return [by[identity] for identity in sorted(trusted)]
        trusted.update(additions)
