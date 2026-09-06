"""Reviewed notes add traceable home changes without altering device evidence."""
import copy
import datetime as dt

import pytest

from modules import RedcapHomeAdjustments as home


def epoch(value):
    return dt.datetime.fromisoformat(value).timestamp()


def event(day=1, hour=12, group='Group A', threshold='167 LFP Power (LSB)', amp='3.00 mA', linked=True):
    return {'id': f'{day}-{hour}-{group}', 'time':epoch(f'2026-08-{day:02}T{hour:02}:00:00-07:00'),
            'kind':'settings_observed', 'phase':'Final', 'evidence':'Original export', 'source_ids':['export'],
            'settings': {'group':[{'label':'Group','value':group}],
                         'left':[{'label':'Upper LFP threshold','value':threshold},
                                 {'label':'Lower LFP threshold','value':'100 LFP Power (LSB)'},
                                 {'label':'Amplitude','value':amp}],
                         'right':[{'label':'Upper LFP threshold','value':threshold},
                                  {'label':'Sensing source hemisphere','value':'Left' if linked else 'Right'},
                                  {'label':'Amplitude','value':'2.00 mA'}]}}


def context(events=None):
    events = events if events is not None else [event()]
    return {'home_transitions':events, 'home_provenance':{'selected_count':len(events)}}


def adjustment(**changes):
    item = dict(date='2026-08-02', time_local='', group='Group A', side='left',
                field='Upper LFP threshold', previous_value='167 LFP Power (LSB)', value='200 LFP Power (LSB)',
                source_url='https://example.org/reviewed-note', note='Reviewed change')
    item.update(changes)
    return item


def apply(ctx=None, items=None, now=None):
    return home.apply(context() if ctx is None else ctx,
                      [adjustment()] if items is None else items,
                      epoch('2026-09-01T00:00:00-07:00') if now is None else now)


def test_day_precision_linked_threshold_provenance_and_nonmutation():
    source = context(); before = copy.deepcopy(source)
    notes = [adjustment()]; original_notes = copy.deepcopy(notes)
    result = apply(source, notes)
    assert source == before and notes == original_notes
    selected = result['home_transitions'][-1]
    assert selected['time'] == epoch('2026-08-02T00:00:00-07:00')
    assert selected['time_precision'] == 'day'
    assert selected['kind'] == 'reviewed_home_adjustment'
    assert selected['source_url'] == notes[0]['source_url']
    assert selected['home_timing']['activation_time_known'] is False
    assert 'Exact time not recorded.' in selected['evidence']
    assert home.value(selected['settings'],'left','Upper LFP threshold') == '200 LFP Power (LSB)'
    assert home.value(selected['settings'],'right','Upper LFP threshold') == '200 LFP Power (LSB)'
    assert home.value(selected['settings'],'right','Amplitude') == '2.00 mA'
    assert result['home_provenance']['selected_count'] == 2
    assert result['home_provenance']['unresolved_adjustments'] == []
    assert len(selected['id']) == 20


def test_exact_time_amplitude_does_not_change_contralateral_channel():
    item = adjustment(time_local='11:23:45', field='Amplitude', previous_value='3.00 mA', value='3.50 mA')
    result = apply(items=[item]); selected=result['home_transitions'][-1]
    assert selected['time'] == epoch('2026-08-02T11:23:45-07:00')
    assert selected['time_precision'] == 'second'
    assert selected['home_timing']['activation_time_known'] is True
    assert 'Time reported in Pacific time.' in selected['evidence']
    assert home.value(selected['settings'],'left','Amplitude') == '3.50 mA'
    assert home.value(selected['settings'],'right','Amplitude') == '2.00 mA'
    assert result['home_provenance']['reviewed_adjustments'][0]['time_precision'] == 'second'


def test_threshold_without_link_does_not_change_contralateral_side_and_missing_field():
    result=apply(context([event(linked=False)]))
    selected=result['home_transitions'][-1]
    assert home.value(selected['settings'],'right','Upper LFP threshold') == '167 LFP Power (LSB)'
    assert home.value(selected['settings'],'right','Missing') is None
    data=copy.deepcopy(selected['settings']); original=copy.deepcopy(data)
    home.update(data,'left','Missing',99)
    assert data == original


def test_future_ignored_and_exact_boundary_is_included():
    when=epoch('2026-08-02T00:00:00-07:00')
    assert len(apply(now=when-1)['home_transitions']) == 1
    assert apply(now=when-1)['home_provenance']['unresolved_adjustments'] == []
    assert len(apply(now=when)['home_transitions']) == 2
    assert apply(items=[])['home_provenance']['reviewed_adjustments'] == []


@pytest.mark.parametrize('ctx,item', [
    (context([]),adjustment()),
    (context([event(2,0)]),adjustment()),
    (context([event(group='Group B')]),adjustment()),
    (context(),adjustment(previous_value='166 LFP Power (LSB)')),
])
def test_preceding_program_mismatch_is_unresolved_and_not_applied(ctx,item):
    before=copy.deepcopy(ctx)
    result=apply(ctx,[item])
    assert result['home_transitions'] == before['home_transitions']
    assert result['home_provenance']['reviewed_adjustments'] == []
    assert 'does not match the preceding' in result['home_provenance']['unresolved_adjustments'][0]['reason']


def test_chained_adjustments_sort_by_day_and_time_before_preceding_validation():
    third=adjustment(date='2026-08-03',time_local='10:00',previous_value='200 LFP Power (LSB)',value='210 LFP Power (LSB)')
    fourth=adjustment(date='2026-08-03',time_local='11:00',previous_value='210 LFP Power (LSB)',value='220 LFP Power (LSB)')
    result=apply(items=[fourth,third,adjustment()])
    assert [home.value(e['settings'],'left','Upper LFP threshold') for e in result['home_transitions']] == [
        '167 LFP Power (LSB)','200 LFP Power (LSB)','210 LFP Power (LSB)','220 LFP Power (LSB)']
    assert result['home_provenance']['selected_count'] == 4
    assert result['home_provenance']['unresolved_adjustments'] == []


def test_stale_later_exports_stay_visible_as_conflicts_until_changed_observation():
    initial=event(1); stale=event(4); changed=event(5,threshold='210 LFP Power (LSB)'); trailing=event(6)
    source=context([trailing,changed,stale,initial]); before=copy.deepcopy(source)
    result=apply(source)
    assert source == before
    by_id={e['id']:e for e in result['home_transitions']}
    conflict=by_id[stale['id']]
    assert home.value(conflict['settings'],'left','Upper LFP threshold') == '200 LFP Power (LSB) (reviewed note); export: 167 LFP Power (LSB)'
    assert home.value(conflict['settings'],'right','Upper LFP threshold').startswith('200 LFP Power (LSB)')
    assert 'Source conflict' in conflict['evidence']
    assert home.value(by_id[changed['id']]['settings'],'left','Upper LFP threshold') == '210 LFP Power (LSB)'
    assert home.value(by_id[trailing['id']]['settings'],'left','Upper LFP threshold') == '167 LFP Power (LSB)'
    assert result['home_provenance']['unresolved_adjustments'] == [{
        'date':'2026-08-02','reason':'Later export conflicts with reviewed home adjustment',
        'source_url':'https://example.org/reviewed-note'}]


@pytest.mark.parametrize('changes', [
    {'date':'bad'},{'time_local':'bad'},{'time_local':'12:00+00:00'},
    {'side':'bilateral'},{'source_url':'http://example.org'},{'source_url':None},
    {'field':'Unknown'},{'previous_value':'167 mA'},{'value':'200'},
    {'value':'-1 LFP Power (LSB)'},{'value':'NaN LFP Power (LSB)'},
    {'value':None},{'note':None},{'note':''},{'group':None},{'group':''},
])
def test_malformed_fields_and_units_rejected_without_changing_program(changes):
    result=apply(items=[adjustment(**changes)])
    assert len(result['home_transitions']) == 1
    assert result['home_provenance']['reviewed_adjustments'] == []
    assert result['home_provenance']['unresolved_adjustments'][0]['reason'] == 'Malformed reviewed home adjustment'


@pytest.mark.parametrize('item', [None,[], 'bad', {}, {k:v for k,v in adjustment().items() if k!='note'}])
def test_malformed_adjustment_entries_fail_closed(item):
    result=apply(items=[item])
    assert len(result['home_transitions']) == 1
    assert result['home_provenance']['reviewed_adjustments'] == []
    assert result['home_provenance']['unresolved_adjustments'][0]['reason'] == 'Malformed reviewed home adjustment'


def test_conflict_propagation_stops_at_different_home_group():
    first=event(1); stale=event(3); switched=event(4,group='Group B'); returned=event(5)
    result=apply(context([returned,switched,stale,first]))
    by_id={e['id']:e for e in result['home_transitions']}
    assert '(reviewed note)' in home.value(by_id[stale['id']]['settings'],'left','Upper LFP threshold')
    assert home.value(by_id[switched['id']]['settings'],'left','Upper LFP threshold') == '167 LFP Power (LSB)'
    assert home.value(by_id[returned['id']]['settings'],'left','Upper LFP threshold') == '167 LFP Power (LSB)'
    assert len(result['home_provenance']['unresolved_adjustments']) == 1


@pytest.mark.parametrize('adjustments', [None,{},'bad'])
def test_nonlist_metadata_is_rejected(adjustments):
    with pytest.raises(ValueError,match='must be a list'):
        home.apply(context(), adjustments, 1e12)


@pytest.mark.parametrize('day,start,end,blocked', [
    ('2026-08-02','2026-08-03','2026-08-05',False),  # before gap
    ('2026-08-03','2026-08-03','2026-08-05',True),   # inclusive start
    ('2026-08-04','2026-08-03','2026-08-05',True),   # inside gap
    ('2026-08-05','2026-08-03','2026-08-05',False),  # exclusive end
    ('2026-08-04','2026-08-03',None,True),          # unresolved ongoing gap
])
def test_reviewed_adjustment_cannot_confirm_unknown_home_program(day,start,end,blocked):
    source=context()
    source['home_unknown_intervals']=[{
        'start':epoch(start+'T00:00:00-07:00'),
        'end':epoch(end+'T00:00:00-07:00') if end else None,
        'reason':'Visit lacks a usable Final snapshot',
    }]
    before=copy.deepcopy(source)
    result=apply(source,[adjustment(date=day)])
    assert source == before
    assert result['home_unknown_intervals'] == before['home_unknown_intervals']
    if blocked:
        assert result['home_transitions'] == before['home_transitions']
        assert result['home_provenance']['reviewed_adjustments'] == []
        assert result['home_provenance']['unresolved_adjustments'] == [{
            'date':day,'reason':'Preceding home program is unknown at the reviewed adjustment'}]
    else:
        assert len(result['home_provenance']['reviewed_adjustments']) == 1
        assert result['home_provenance']['unresolved_adjustments'] == []
