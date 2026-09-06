"""Import the existing Percept historical survey tables as separate BRAVO forms.

Each instrument keeps its own timestamp, completion flag and outcome meaning.
The fixed upstream tables are copied unchanged and remain available for audit.
"""
import csv
import hashlib
import os
from pathlib import Path
from django.db import transaction
from Server import models
from modules.RCS08SurveyProcessing import STANDARD_MPQ, SENSORY_MPQ, AFFECTIVE_MPQ, EXTRA_MPQ

TIMELINE_SCHEMA = "redcap-pretrial-1"

# field, display label, upper bound (all listed scales have a lower bound of zero)
FLUCTUATION = [
    ('Pain and mood', 'pain_mood_timestamp', 'pain_mood_complete', [
        ('nrs_intensity','NRS pain intensity',10),('nrs_unpleasantness','NRS unpleasantness',10),
        ('vas_intensity','VAS pain intensity',100),('vas_unpleasantness','VAS unpleasantness',100),('mood_vas','Mood VAS',100)]),
    ('MPQ', 'mpq_timestamp', 'mpq_complete', [
        ('mpq_sens','MPQ sensory',33),('mpq_aff','MPQ affective',12),('mpq_standard_0_45','Standard MPQ',45),
        *[(f'mpq_{name}', name.replace('_', ' ').capitalize(), 3) for name in STANDARD_MPQ]]),
    ('Pain regions', 'pain_regions_timestamp', 'pain_regions_complete', [
        ('worst_pain_nrs_intensity','Worst-site NRS intensity',10),('worst_pain_vas_intensity','Worst-site VAS intensity',100),
        ('best_pain_nrs_intensity','Best-site NRS intensity',10),('best_pain_vas_intensity','Best-site VAS intensity',100)]),
    ('Left leg and low back', 'left_leg_low_back_timestamp', 'left_leg_low_back_complete', [
        ('left_leg_low_back_nrs_intensity','Left leg / low back NRS intensity',10),
        ('left_leg_low_back_vas_intensity','Left leg / low back VAS intensity',100)]),
]
STAGE0 = [
    ('Mini VAS', 'stage_0_mini_vas_timestamp', 'stage_0_mini_vas_complete', [
        ('pain_vas_mini','Pain VAS',100),('head_pain_vas_mini','Head pain VAS',100),
        ('scs_pain_vas_mini','SCS pain VAS',100),('pain_relief_mini','Pain relief VAS',100)]),
    ('Short NRS VAS', 'stage_0_short_nrsvas_timestamp','stage_0_short_nrsvas_complete', [
        ('pain_nrs_short','Pain NRS',10),('pain_vas_short','Pain VAS',100),('head_pain_vas_short','Head pain VAS',100),
        ('scs_pain_vas_short','SCS pain VAS',100),('unpleasantness_vas_short','Unpleasantness VAS',100),
        ('relief_vas_short','Relief VAS',100),('depression_vas_short','Depression VAS',100)]),
    ('Long NRS VAS MPQ','stage_0_long_nrsvasmpq_timestamp','stage_0_long_nrsvasmpq_complete', [
        ('pain_nrs_long','Pain NRS',10),('pain_vas_long','Pain VAS',100),
        ('unpleasantness_vas_long','Unpleasantness VAS',100),('sf_mpq_sum','Expanded 18-item MPQ total',54),
        ('mpq_standard_0_45','Standard MPQ',45),('mpq_sens','MPQ sensory',33),('mpq_aff','MPQ affective',12),
        *[(f'mpq_{name}', name.replace('_', ' ').capitalize(), 3) for name in STANDARD_MPQ],
        *[(name, 'Fiery' if name == 'firey' else name.capitalize(), 3) for name in EXTRA_MPQ]]),
    ('SF36','sf36_timestamp','sf36_complete',[(key,label,100) for key,label in [
        ('phys_func_score_sf36','Physical functioning'),('role_limit_score_sf36','Role limitations'),
        ('emot_prob_score_sf36','Emotional problems'),('energy_score_sf36','Energy'),('emotional_score_sf36','Emotional wellbeing'),
        ('social_score_sf36','Social functioning'),('pain_score_sf36','Pain'),('general_health_sf36','General health')]]),
    ('BPI','brief_pain_inventory_timestamp','brief_pain_inventory_complete',[
        ('pain_severity_score_bpi','Stored BPI severity score',None),('pain_interference_score_bpi','Stored BPI interference score',None)]),
    ('HAMD','hamilton_selfrating_scale_for_depression_hamd_timestamp','hamilton_selfrating_scale_for_depression_hamd_complete',[
        ('hamd_score','Stored HAMD score',None)]),
]


STAGE0_BLOCKS = {'mpq_standard_0_45': STANDARD_MPQ, 'mpq_sens': SENSORY_MPQ,
                 'mpq_aff': AFFECTIVE_MPQ}


def source_columns(family, key):
    """Declare the fixed-table inputs behind every stored score."""
    if family == 'Stage 0':
        if key in STAGE0_BLOCKS:
            return [f'{name}_stage0' for name in STAGE0_BLOCKS[key]]
        if key in {f'mpq_{name}' for name in STANDARD_MPQ}:
            return [f'{key[4:]}_stage0']
        if key in EXTRA_MPQ:
            return [f'{key}_stage0']
    return [key]


def historical_value(row, family, key):
    from modules.RCS08Sync import _number
    values = [_number(row.get(column)) for column in source_columns(family, key)]
    if family == 'Stage 0' and key in STAGE0_BLOCKS:
        # Exact notebook rule: partial blocks sum observed items, all-missing stays missing.
        return sum(value for value in values if value is not None) if any(value is not None for value in values) else None
    return values[0]


def prepare_forms(rules_dir=None):
    from modules.RCS08Sync import _number, _redcap_timestamp
    from dateutil.parser import parse
    rules=Path(rules_dir or os.environ.get('RCS08_PROCESSING_RULES','/run/secrets/rcs08_processing'))
    prepared=[]
    for filename, family, identity, definitions in (
        ('rcs08_fluctuation_redcap.csv','Fluctuation','participant_id',FLUCTUATION),
        ('rcs08_stage0_redcap.csv','Stage 0','record_id',STAGE0)):
        path=rules/filename
        raw=path.read_bytes()
        with path.open(encoding='utf-8-sig',newline='') as handle: rows=list(csv.DictReader(handle))
        patient=[row for row in rows if row[identity]=='RCS08']
        for label,timestamp,complete,metrics in definitions:
            name=f'RCS08 {family} - {label}'
            required={timestamp,complete,*[column for key,_,_ in metrics for column in source_columns(family, key)]}
            missing=required-set(rows[0]) if rows else required
            if missing: raise ValueError(f'{filename}: missing columns for {label}: {sorted(missing)}')
            records=[];invalid_time=0
            for row in patient:
                if _number(row.get(complete))!=2: continue
                try: epoch,iso=_redcap_timestamp(parse(row[timestamp]).isoformat())
                except (ValueError,TypeError,OverflowError): invalid_time+=1; continue
                values=[historical_value(row, family, key) for key,_,_ in metrics]
                for value,(_,field,maximum) in zip(values,metrics):
                    if value is not None and (value < 0 or (maximum is not None and value > maximum)): raise ValueError(f'{name}: {field} outside documented range')
                if all(value is None for value in values): continue
                key=':'.join(str(row.get(k,'')) for k in ('source_record_id','source_event','redcap_event_name','redcap_repeat_instrument','redcap_repeat_instance'))
                records.append({'date':epoch,'name':key,'record':[values+[iso]]})
            records.sort(key=lambda item:(item['date'],item['name']))
            if not records: continue
            questions=[{'variableName':key,'text':label,'type':'score','min':0,**({'max':maximum} if maximum is not None else {}),'step':1,'show':True,'activeView':index==0} for index,(key,label,maximum) in enumerate(metrics)]
            questions.append({'variableName':timestamp,'text':'Time','type':'text','show':False})
            audit={'pipeline':'Percept fixed historical table','source_file':filename,
                   'timeline_schema':TIMELINE_SCHEMA, 'completion':'complete = 2',
                   'mpq_scoring':'Stage 0: sum observed items; wholly absent blocks remain missing',
                   'source_sha256':hashlib.sha256(raw).hexdigest(),'patient_rows':len(patient),
                   'included':len(records),'invalid_completed_timestamps':invalid_time}
            prepared.append((name,[{'header':name,'questions':questions,'processing':audit}],records))
    return prepared


def sync_historical_surveys(participant, *, dry_run=False):
    from modules.RCS08Sync import _records_signature
    from modules.ReportCache import invalidate
    prepared=prepare_forms()  # Validate every input before publishing any changes.
    results=[]
    with transaction.atomic():
        for name,mapping,records in prepared:
            form=models.ScaleForms.find(institute=participant.institute,name=name)
            stored=[] if form is None else [
                {'date':r.date,'name':r.name,'record':r.record} for r in models.ScaleRecord.find_all(source=form,participant=participant)]
            stored.sort(key=lambda item:(item['date'],item['name']))
            changed=not form or form.record!=mapping or _records_signature(records)!=_records_signature(stored)
            if changed and not dry_run:
                if form is None: form=models.ScaleForms(institute=participant.institute,name=name,record_version=1)
                form.record_type='REDCap API Sync';form.record=mapping;form.save()
                if not models.ParticipantLinkRel.include(participant=participant,record=form): models.ParticipantLinkRel.create(participant,form)
                models.ScaleRecord.objects.filter(source=form,participant=participant).delete()
                models.ScaleRecord.objects.bulk_create([models.ScaleRecord(participant=participant,source=form,**row) for row in records])
                invalidate()
            results.append({'form':name,'records':len(records),'changed':changed,'written':len(records) if changed and not dry_run else 0})
    return results
