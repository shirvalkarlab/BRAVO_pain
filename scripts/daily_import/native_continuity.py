"""Pure native-measurement continuity, subordinate to authenticated device policy.

This is not a serial identity rule. The caller binds both reports to authenticated
bytes, one owner/implant and canonical clock provenance before admission. No raw
arrays are changed. Missing PSD/contact claims remain observations, not overwrites.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math

POLICY_VERSION = 'bilateral-native-continuity-v1'
SIDES = ('left', 'right')
SIDE_KEYS = {'HemisphereLocationDef.Left':'left', 'HemisphereLocationDef.Right':'right'}
KINDS = ('chronic', 'psd')


class ContinuityError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _same(left, right):
    # Python considers True == 1; explicit JSON boolean and numeric claims differ.
    return _digest(left) == _digest(right)


def _integer(value):
    return type(value) is int and value >= 0


def _numeric(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _time(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            return dt.timestamp()
    except (TypeError, ValueError, AttributeError, OverflowError):
        pass
    raise ContinuityError('invalid_native_time')


def _key(row):
    if not isinstance(row, dict) or not _integer(row.get('DateTimeBlockId')) or not _integer(row.get('DateTimeOffsetInSeconds')):
        raise ContinuityError('invalid_native_key')
    _time(row.get('DateTime'))
    return row['DateTimeBlockId'], row['DateTimeOffsetInSeconds']


def _intrinsic(value):
    if isinstance(value, dict):
        native = 'DateTimeBlockId' in value or 'DateTimeOffsetInSeconds' in value
        if native:
            _key(value)
        if any(not isinstance(k, str) for k in value):
            raise ContinuityError('invalid_json_key')
        return {key:_intrinsic(item) for key,item in value.items() if not(native and key == 'DateTime')}
    if isinstance(value, list):
        return [_intrinsic(item) for item in value]
    if type(value) in (int, float):
        if not _numeric(value):
            raise ContinuityError('nonfinite_measurement')
        # Never round exact JSON integers through binary floating point. Equal
        # integral float encodings can share one digest without losing big ints.
        return int(value) if type(value) is float and value.is_integer() else value
    if value is None or type(value) in (str, bool):
        return value
    raise ContinuityError('invalid_measurement_type')


def _insert(index, key, row, check_clock=False):
    normal = _intrinsic(row)
    if key in index and not _same(index[key]['normal'], normal):
        raise ContinuityError('ambiguous_native_duplicate')
    if key in index and check_clock and _clock_nodes(index[key]['raw']) != _clock_nodes(row):
        raise ContinuityError('canonical_duplicate_clock_conflict')
    index[key] = {'raw':row, 'normal':normal}


def _spectrum(row):
    _key(row)
    frequency, power = row.get('Frequency'), row.get('FFTBinData')
    if (not isinstance(frequency, list) or not isinstance(power, list) or len(frequency) != len(power)
            or len(frequency) < 2 or not all(_numeric(x) for x in frequency+power)
            or frequency[0] < 0 or any(a >= b for a,b in zip(frequency, frequency[1:]))):
        raise ContinuityError('invalid_spectrum')
    if 'SenseID' in row and not isinstance(row['SenseID'], str):
        raise ContinuityError('invalid_contact_claim')
    return len(set(power)) > 1 and any(x != 0 for x in power)


def _extract(report, check_clock=False):
    if not isinstance(report, dict) or not isinstance(report.get('DiagnosticData'), dict):
        raise ContinuityError('measurement_inventory_unavailable')
    diag = report['DiagnosticData']
    chronic = {side:{} for side in SIDES}
    logs = diag.get('LFPTrendLogs', {})
    if not isinstance(logs, dict):
        raise ContinuityError('invalid_chronic_inventory')
    for hemisphere, days in logs.items():
        if hemisphere not in SIDE_KEYS or not isinstance(days, dict):
            raise ContinuityError('invalid_chronic_hemisphere')
        for rows in days.values():
            if not isinstance(rows, list):
                raise ContinuityError('invalid_chronic_inventory')
            for row in rows:
                key = _key(row)
                if not _numeric(row.get('LFP')) or not _numeric(row.get('AmplitudeInMilliAmps')):
                    raise ContinuityError('incomplete_chronic_measurement')
                _insert(chronic[SIDE_KEYS[hemisphere]], key, row, check_clock)
    psd = {}
    snapshots = diag.get('LfpFrequencySnapshotEvents', [])
    if not isinstance(snapshots, list):
        raise ContinuityError('invalid_psd_inventory')
    for row in snapshots:
        native = _key(row)
        if not _integer(row.get('EventID')):
            raise ContinuityError('invalid_psd_event_identity')
        payloads = row.get('LfpFrequencySnapshotEvents', {})
        if not isinstance(payloads, dict) or any(side not in SIDE_KEYS for side in payloads):
            raise ContinuityError('invalid_psd_hemisphere')
        for payload in payloads.values():
            _spectrum(payload)
        _insert(psd, (*native,row['EventID']), row, check_clock)
    measurements = {side:{} for side in SIDES}
    for entry in psd.values():
        for hemisphere,payload in entry['raw'].get('LfpFrequencySnapshotEvents', {}).items():
            _insert(measurements[SIDE_KEYS[hemisphere]], _key(payload), payload, check_clock)
    return chronic, psd, measurements


def _compatible_payload(x, y):
    if _same(x, y):
        return False
    # Only an absent/empty contact identifier may weaken or add an observation.
    # Every number, native clock, group and other explicit field must agree.
    if (not _same({k:v for k,v in x.items() if k != 'SenseID'}, {k:v for k,v in y.items() if k != 'SenseID'})
            or x.get('SenseID') and y.get('SenseID')):
        raise ContinuityError('shared_psd_measurement_conflict')
    return True


def _event_logs(report, check_clock=False):
    """Retain simultaneous status events as a set; logs are never witnesses."""
    rows = report['DiagnosticData'].get('EventLogs', [])
    if not isinstance(rows, list):
        raise ContinuityError('invalid_event_log_inventory')
    index = {}
    for row in rows:
        native = _key(row)
        families = [key for key in ('ParameterTrendId','SessionType','RechargeSessionType','MriType') if key in row]
        if len(families) != 1 or not isinstance(row[families[0]], str) or not row[families[0]]:
            raise ContinuityError('unknown_event_log_category')
        family = families[0]
        category = row[family] if family == 'ParameterTrendId' else ''
        normal = _intrinsic(row)
        # Native logs genuinely contain ON/OFF or start/end at the same instant.
        # Preserve that set rather than selecting one value or inventing a side.
        group = index.setdefault((*native,family,category), {})
        digest = _digest(normal)
        if digest in group and check_clock and _clock_nodes(group[digest]['raw']) != _clock_nodes(row):
            raise ContinuityError('canonical_duplicate_clock_conflict')
        group[digest] = {'raw':row, 'normal':normal}
    return index


def _shared_event_logs(candidate, reference):
    rows = []
    for key in sorted(candidate.keys() & reference.keys()):
        if candidate[key].keys() != reference[key].keys():
            raise ContinuityError('shared_event_log_conflict')
        rows.extend((key,candidate[key][digest]['raw'],reference[key][digest]['raw']) for digest in sorted(candidate[key]))
    return rows


def _shared_psd(candidate, reference, cm, rm):
    """Check event context and actual spectrum keys, independently of event labels."""
    exact = {side:[] for side in SIDES}
    weakening = {'candidate_omitted_psd_sides':0, 'reference_omitted_psd_sides':0, 'blank_contact_claims':0}
    for key in sorted(candidate.keys() & reference.keys()):
        a, b = candidate[key]['normal'], reference[key]['normal']
        if not _same({k:v for k,v in a.items() if k != 'LfpFrequencySnapshotEvents'}, {k:v for k,v in b.items() if k != 'LfpFrequencySnapshotEvents'}):
            raise ContinuityError('shared_psd_context_conflict')
        ap, bp = a.get('LfpFrequencySnapshotEvents', {}), b.get('LfpFrequencySnapshotEvents', {})
        for hemisphere in SIDE_KEYS:
            x, y = ap.get(hemisphere), bp.get(hemisphere)
            if x is None or y is None:
                if x is None and y is not None:
                    weakening['candidate_omitted_psd_sides'] += 1
                if y is None and x is not None:
                    weakening['reference_omitted_psd_sides'] += 1
            else:
                _compatible_payload(x,y)
    # A spectrum's own block/offset identifies the physical measurement. An
    # event can reattach one spectrum at several outer event times or labels;
    # those copies cannot inflate witnesses or hide a conflicting measurement.
    for side in SIDES:
        for key in sorted(cm[side].keys() & rm[side].keys()):
            a, b = cm[side][key], rm[side][key]
            if _compatible_payload(a['normal'],b['normal']):
                weakening['blank_contact_claims'] += 1
            elif _spectrum(a['raw']):
                exact[side].append((key,a['normal']))
    return exact, weakening


def _witness(rows, kind):
    blocks = defaultdict(list)
    for key, payload in rows:
        blocks[key[0]].append((key,payload))
    eligible = []
    for block, entries in blocks.items():
        offsets = {key[1] for key,_ in entries}
        if len(offsets) < 2:
            continue
        if kind == 'chronic' and len({row['LFP'] for _,row in entries}) < 2:
            continue
        eligible.append((block, entries))
    if not eligible:
        raise ContinuityError('insufficient_'+kind+'_continuity')
    # One common native block supplies a real interval; deterministic selection
    # does not turn copies or different EventIDs at one instant into more time.
    block, entries = max(eligible, key=lambda pair:(len(pair[1]), pair[0]))
    entries = sorted(entries)
    return {'count':len(entries), 'block':block, 'first_offset':min(k[1] for k,_ in entries),
            'last_offset':max(k[1] for k,_ in entries), 'native_keys_sha256':_digest([key for key,_ in entries]),
            'payloads_sha256':_digest(entries)}


def prove_continuity(candidate_report, reference_report):
    """Require bilateral chronic and nontrivial full PSD continuity; no identity I/O."""
    ac, ap, am = _extract(candidate_report)
    bc, bp, bm = _extract(reference_report)
    ae, be = _event_logs(candidate_report), _event_logs(reference_report)
    _shared_event_logs(ae, be)
    exact = {side:[] for side in SIDES}
    for side in SIDES:
        for key in sorted(ac[side].keys() & bc[side].keys()):
            x, y = ac[side][key]['normal'], bc[side][key]['normal']
            if not _same(x, y):
                raise ContinuityError('shared_chronic_measurement_conflict')
            if x['LFP'] > 0 and x['AmplitudeInMilliAmps'] >= 0:
                exact[side].append((key,x))
    psd, weakening = _shared_psd(ap, bp, am, bm)
    witnesses = {'chronic':{side:_witness(exact[side], 'chronic') for side in SIDES},
                 'psd':{side:_witness(psd[side], 'psd') for side in SIDES}}
    serial = lambda c,p,m,e:{'chronic':{s:sorted((k,v['normal']) for k,v in c[s].items()) for s in SIDES}, 'psd':sorted((k,v['normal']) for k,v in p.items()), 'psd_measurements':{s:sorted((k,v['normal']) for k,v in m[s].items()) for s in SIDES}, 'event_logs':sorted((k,sorted(v)) for k,v in e.items())}
    proof = {'policy_version':POLICY_VERSION, 'candidate_intrinsic_sha256':_digest(serial(ac,ap,am,ae)),
             'reference_intrinsic_sha256':_digest(serial(bc,bp,bm,be)), 'witnesses':witnesses, 'weakening':weakening,
             'candidate_records':{'chronic':{s:len(ac[s]) for s in SIDES}, 'psd':len(ap)},
             'reference_records':{'chronic':{s:len(bc[s]) for s in SIDES}, 'psd':len(bp)}}
    proof['proof_sha256'] = _digest(proof)
    validate_receipt(proof)
    return proof


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_receipt(proof):
    """Validate stored proof structure; the caller authenticates its source bindings."""
    keys = {'policy_version','candidate_intrinsic_sha256','reference_intrinsic_sha256','witnesses','weakening','candidate_records','reference_records','proof_sha256'}
    try:
        if (not isinstance(proof, dict) or set(proof) != keys or proof['policy_version'] != POLICY_VERSION
                or not all(_sha(proof[k]) for k in ('candidate_intrinsic_sha256','reference_intrinsic_sha256','proof_sha256'))
                or _digest({k:v for k,v in proof.items() if k != 'proof_sha256'}) != proof['proof_sha256']):
            raise ValueError
        if set(proof['witnesses']) != set(KINDS) or set(proof['weakening']) != {'candidate_omitted_psd_sides','reference_omitted_psd_sides','blank_contact_claims'}:
            raise ValueError
        if any(not _integer(n) for n in proof['weakening'].values()):
            raise ValueError
        for record_field in ('candidate_records','reference_records'):
            counts = proof[record_field]
            if set(counts) != set(KINDS) or set(counts['chronic']) != set(SIDES) or not _integer(counts['psd']):
                raise ValueError
            if any(not _integer(n) for n in counts['chronic'].values()):
                raise ValueError
        for kind in KINDS:
            if set(proof['witnesses'][kind]) != set(SIDES):
                raise ValueError
            for side in SIDES:
                w = proof['witnesses'][kind][side]
                if (set(w) != {'count','block','first_offset','last_offset','native_keys_sha256','payloads_sha256'}
                        or any(not _integer(w[k]) for k in ('count','block','first_offset','last_offset'))
                        or w['count'] < 2 or w['first_offset'] >= w['last_offset']
                        or not _sha(w['native_keys_sha256']) or not _sha(w['payloads_sha256'])):
                    raise ValueError
                for field in ('candidate_records','reference_records'):
                    total = proof[field]['chronic'][side] if kind == 'chronic' else proof[field]['psd']
                    if w['count'] > total:
                        raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ContinuityError('invalid_continuity_receipt') from None
    return True


def _clock_nodes(value, path=''):
    result = {}
    if isinstance(value, dict):
        if 'DateTimeBlockId' in value or 'DateTimeOffsetInSeconds' in value:
            key = _key(value)
            result[(path,*key)] = _time(value['DateTime'])
        for key,item in value.items():
            result.update(_clock_nodes(item,path+'/'+key))
    elif isinstance(value, list):
        for index,item in enumerate(value):
            result.update(_clock_nodes(item,path+'/'+str(index)))
    return result


def verify_clock_agreement(candidate_canonical, reference_canonical):
    """Called only after canonical conversion against the authenticated implant table."""
    ac, ap, am = _extract(candidate_canonical, check_clock=True)
    bc, bp, bm = _extract(reference_canonical, check_clock=True)
    ae, be = _event_logs(candidate_canonical, check_clock=True), _event_logs(reference_canonical, check_clock=True)
    records = []
    for side in SIDES:
        records.extend(('chronic/'+side, key,ac[side][key]['raw'],bc[side][key]['raw']) for key in ac[side].keys() & bc[side].keys())
    records.extend(('psd-event',key,{k:v for k,v in ap[key]['raw'].items() if k != 'LfpFrequencySnapshotEvents'},
                    {k:v for k,v in bp[key]['raw'].items() if k != 'LfpFrequencySnapshotEvents'}) for key in ap.keys() & bp.keys())
    for side in SIDES:
        records.extend(('psd-measurement/'+side,key,am[side][key]['raw'],bm[side][key]['raw']) for key in am[side].keys() & bm[side].keys())
    records.extend(('event-log',key,a,b) for key,a,b in _shared_event_logs(ae,be))
    clocks = []
    for kind,key,a,b in records:
        x, y = _clock_nodes(a), _clock_nodes(b)
        for native in x.keys() & y.keys():
            if x[native] != y[native]:
                raise ContinuityError('canonical_measurement_clock_conflict')
            clocks.append((kind,key,native,x[native]))
    if not clocks:
        raise ContinuityError('canonical_clock_overlap_unavailable')
    receipt = {'policy_version':POLICY_VERSION,'shared_clock_nodes':len(clocks),'clock_observations_sha256':_digest(sorted(clocks))}
    receipt['proof_sha256'] = _digest(receipt)
    validate_clock_receipt(receipt)
    return receipt


def validate_clock_receipt(receipt):
    """Validate the compact canonical-clock certificate, not an arbitrary blob."""
    try:
        if (not isinstance(receipt, dict) or set(receipt) != {'policy_version','shared_clock_nodes','clock_observations_sha256','proof_sha256'}
                or receipt['policy_version'] != POLICY_VERSION or not _integer(receipt['shared_clock_nodes'])
                or receipt['shared_clock_nodes'] < 8
                or not _sha(receipt['clock_observations_sha256']) or not _sha(receipt['proof_sha256'])
                or _digest({k:v for k,v in receipt.items() if k != 'proof_sha256'}) != receipt['proof_sha256']):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ContinuityError('invalid_canonical_clock_receipt') from None
    return True
