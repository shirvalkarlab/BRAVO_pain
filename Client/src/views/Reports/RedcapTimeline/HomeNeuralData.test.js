import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import HomeNeuralData, {NeuralAnalysisPolicy} from './HomeNeuralData';
const SYNTHETIC_PARTICIPANT = 'synthetic-participant';
let mockQuery, mockProps;
jest.mock('./useHomeNeuralTimeline',()=>({useHomeNeuralTimeline:(...props)=>{mockProps=props;return mockQuery;}}));
jest.mock('./HomeNeuralChart',()=>({__esModule:true,default:({panel,window,onSegment})=><div data-panel={`${window.id}:${panel.side}`}>
 {panel.segments.map(s=><button key={s.id} onClick={()=>onSegment(s.id)}>Inspect {s.id}</button>)}
</div>}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role,variant})=><div role={role} data-heading={variant}>{children}</div>}));
const time=Date.parse('2026-09-02T00:00:00-07:00')/1000;
const settings={group:[{label:'Group',value:'D'}],left:[{label:'Tablet target',value:'Left GPi'},{label:'Sensing source hemisphere',value:'Right'},{label:'Stimulation contacts',value:'2−, Case+'},{label:'Sensing contacts',value:'1–3'}],right:[{label:'Tablet target',value:'Right VIM'}]};
const segment=id=>({id,start:time,end:time+86400,mode:'Closed loop · single threshold',power_band_label:'13.67 Hz center',sensing_side:'right',settings,evidence:'Reviewed source snapshot'});
const window=id=>({id,start:time-(id==='previous'?864000:0),end:time+(id==='previous'?0:86400),panels:['left','right'].map(side=>({side,segments:[segment(`${id}-${side}-1`),segment(`${id}-${side}-2`)]}))});
let root,element;
const mount=async()=>act(async()=>root.render(<HomeNeuralData participant={SYNTHETIC_PARTICIPANT}/>));
const click=async(text)=>{const button=[...element.querySelectorAll('button')].find(n=>n.textContent===text);expect(button).toBeDefined();await act(async()=>button.click());};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockQuery={data:{windows:[window('current'),window('previous')]},loading:false,error:''};element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});
test('four ordered panels identify stimulated sides and preserve original data under current and previous visits',async()=>{
 await mount();expect([...element.querySelectorAll('[data-panel]')].map(x=>x.dataset.panel)).toEqual(['current:left','current:right','previous:left','previous:right']);
 expect(element.textContent).toContain('10 minutes');expect(element.textContent).toContain('opposite side');
 expect(element.textContent).toContain('Left · biomarker');expect(element.textContent).toContain('Right · biomarker');
 expect(element.textContent).not.toContain('rolling median');expect(element.querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
 expect(mockProps).toEqual([SYNTHETIC_PARTICIPANT,[0,0],undefined,true]);await click('Refresh neural view');expect(mockProps[1]).toEqual([0,1]);
});
test('plot selection opens exact interval source details, maps UI targets, and supports collapse',async()=>{
 await mount();await click('Inspect current-left-1');
 expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
 expect(element.textContent).toContain('Reviewed source snapshot');expect(element.textContent).not.toContain('Left GPi');expect(element.textContent).not.toContain('Right VIM');
 await act(async()=>element.querySelector('.MuiAccordionSummary-root').click());expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('false');
});
test('settings selector chooses an interval independently of plot interaction',async()=>{
 await mount();const input=element.querySelector('input[role="combobox"]');
 await act(async()=>{input.focus();input.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));});
 const option=document.querySelector('[role="option"]');expect(option).not.toBeNull();
 await act(async()=>option.dispatchEvent(new MouseEvent('click',{bubbles:true})));
 expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
});
test('loading and failed requests do not show stale panels; refresh disabled only during loading',async()=>{
 mockQuery={data:null,loading:true,error:''};await mount();expect(element.querySelector('[role="status"]')).not.toBeNull();expect(element.querySelector('button').disabled).toBe(true);expect(element.querySelector('[data-panel]')).toBeNull();
 mockQuery={data:null,loading:false,error:'Read access denied'};await mount();expect(element.textContent).toContain('Read access denied');expect(element.querySelector('button').disabled).toBe(false);
});
test('missing calendar, one visit, and absent side recordings each have explicit empty states',async()=>{
 mockQuery={data:{windows:[],message:'Calendar unavailable'},loading:false,error:''};await mount();expect(element.textContent).toContain('Calendar unavailable');
 mockQuery.data={};await mount();expect(element.textContent).toContain('calendar is needed');
 mockQuery.data={windows:[{...window('current'),panels:[{side:'left',segments:[]},{side:'right',segments:[]}]}]};await mount();
 expect(element.textContent).toContain('Only one reviewed stimulation visit');expect(element.querySelectorAll('[data-panel]')).toHaveLength(2);expect(element.textContent).toContain('No eligible home recordings');
});


test('unrecorded settings remain empty and threshold uncertainty stays explicit',async()=>{
 const only=window('current');only.panels[0].segments=[{...segment('unknown'),settings:{},threshold_status:'Final single threshold not resolved'}];
 mockQuery.data={windows:[only]};await mount();await click('Inspect unknown');
 expect(element.textContent).toContain('Final single threshold not resolved');
});


test('full source details display sensing contact pairs as discrete contacts while retaining original settings',async()=>{
 await mount();await click('Inspect current-left-1');
 expect(element.textContent).toContain('1 and 3');
 expect(element.textContent).not.toContain('1–3');
 expect(settings.left.find(row=>row.label==='Sensing contacts').value).toBe('1–3');
 expect(element.querySelector('input[role="combobox"]').value).toContain('Right lead');
 expect(element.querySelector('input[role="combobox"]').value).toContain('13.67 Hz center');
});

test('historical coverage keeps current dates explicit and displays the unchanged supported previous period',async()=>{
 const current=window('current'),previous=window('previous');
 current.coverage={status:'outside',start:null,end:null};
 previous.coverage={status:'covered',start:previous.start,end:previous.end};
 mockQuery.data={windows:[current,previous],neural_scope:{coverage_start:previous.start,coverage_end:previous.end,description:'Native observations outside documented testing dates, including home-testing days.'}};
 await mount();
 expect(element.textContent).toContain('This visit period is outside the reviewed historical range');
 expect(element.textContent).toContain('Its dates have not been changed');
 expect(element.textContent).toContain('These observations do not verify physical location');
 expect(element.textContent).toContain('end excluded');
 expect(element.textContent).toContain('The controlling stimulation side is not inferred');
 expect(element.textContent).not.toContain('Each panel follows the stimulated side');
 expect(element.textContent).toContain('Native observations outside documented testing dates');
 expect([...element.querySelectorAll('[data-panel]')].map(x=>x.dataset.panel)).toEqual(['previous:left','previous:right']);
 expect(element.querySelector('[aria-label="current stimulation visit period"]')).not.toBeNull();
 expect(current.start).toBe(time);
});

test('partial coverage shows its supported range without altering the plotted period',async()=>{
 const current=window('current');current.coverage={status:'partial',start:current.start,end:current.end-100};
 mockQuery.data={windows:[current],neural_scope:{coverage_start:current.start,coverage_end:current.end-100,description:'Historical scope.'}};
 await mount();expect(element.textContent).toContain('the remaining dates are unavailable');
 expect([...element.querySelectorAll('[data-panel]')].map(x=>x.dataset.panel)).toEqual(['current:left','current:right']);
});

const observed = id => ({...window(id),display_basis:'recorded_observations',label:`${id} observations`,
 coverage_basis:'recorded_sample_envelope',coverage:{start:time+100,end:time+1000},
 panels:['left','right'].map(side=>({side,segments:[{...segment(`observed-${id}-${side}`),mode:'Not established',thresholds:[],
  evidence:'Physical location and at-home status are unverified; testing-calendar completeness is unverified.',
  points:[{time:time+100,power:8,amplitude:2}]}]}))});

test('recent recorded current observations precede unchanged reviewed periods with explicit evidence boundaries',async()=>{
 const current=window('current'),previous=window('previous');current.coverage={status:'outside'};
 const recent=observed('current');const original=JSON.stringify([current,previous,recent]);
 mockQuery.data={windows:[current,previous],observation_windows:[recent],
  observation_scope:{start:time,end:time+86400,description:'Native source observations only.'},
  neural_scope:{coverage_start:previous.start,coverage_end:previous.end,description:'Reviewed historical range.'}};
 await mount();
 const section=element.querySelector('[aria-label="Recent recorded observations"]');
 expect(section).not.toBeNull();expect(section.textContent).toContain('Physical location and at-home status are unverified');
 expect(section.textContent).toContain('testing calendar may be incomplete');expect(section.textContent).toContain('Known testing days and overlapping averaging bins are excluded');
 expect(section.textContent).toContain('not a reviewed at-home analysis');expect(section.textContent).toContain('Requested period:');
 expect(section.textContent).toContain('Recorded coverage:');expect(section.textContent).toContain('not evidence of continuous recording');
 expect(section.textContent).toContain('Current observations');expect(section.textContent).toContain('native recorded neural power');
 expect(section.textContent).toContain('The controlling stimulation side is not inferred');
 expect(section.textContent).not.toContain('eligible home');
 expect([...element.querySelectorAll('[data-panel]')].map(x=>x.dataset.panel)).toEqual(['current:left','current:right','previous:left','previous:right']);
 expect(element.textContent).toContain('Reviewed historical periods');expect(element.textContent).toContain('outside the reviewed historical range');
 expect(JSON.stringify([current,previous,recent])).toBe(original);
 await click('Inspect observed-current-left');expect(section.textContent).toContain('testing-calendar completeness is unverified');
});

test('selected observational periods remain distinct and empty or untyped observations do not show misleading plots',async()=>{
 const selected=observed('selected');
 mockQuery.data={windows:[],observation_windows:[selected]};await mount();
 expect(element.textContent).toContain('Selected observations');expect(element.textContent).not.toContain('Reviewed historical periods');
 expect(element.querySelector('[aria-label="selected recorded observations"]')).not.toBeNull();
 mockQuery.data.observation_windows=[{...selected,panels:[{side:'left',segments:[]}]}];await mount();
 expect(element.querySelector('[aria-label="Recent recorded observations"]')).toBeNull();
 mockQuery.data.observation_windows=[{...selected,display_basis:'unreviewed_other'}];await mount();
 expect(element.querySelector('[aria-label="Recent recorded observations"]')).toBeNull();
});

test('observational views use actual plotting eligibility and retain measured zero without requiring both metrics',async()=>{
 const recent=observed('current');recent.panels[0].segments[0].points=[{time:time+100,power:0,amplitude:null}];
 recent.panels[1].segments[0].points=[{time:time+100,power:null,amplitude:0}];
 delete recent.coverage_basis;
 mockQuery.data={windows:[],observation_windows:[recent]};await mount();
 expect(element.querySelectorAll('[data-panel]')).toHaveLength(2);expect(element.textContent).not.toContain('Recorded coverage:');
 recent.panels[0].segments[0].points[0].power_conflict=true;
 recent.panels[1].segments[0].points[0].amplitude_conflict=true;
 await mount();expect(element.querySelector('[aria-label="Recent recorded observations"]')).toBeNull();
});

test.each(['stored_snapshot','unavailable','invalid','unknown'])('clinic provenance %s stays explicit without claiming upstream freshness',async(calendar_status)=>{
 mockQuery.data={windows:[],observation_provenance:{calendar_status,calendar_built_at:calendar_status==='stored_snapshot'?'2026-10-18T12:00:00Z':null,message:'Calendar completeness has not been reviewed.'}};
 mockQuery.freshnessError='Automatic update check unavailable';await mount();
 expect(element.textContent).toContain('does not confirm the latest upstream sync succeeded');
 expect(element.textContent).toContain('Testing-calendar completeness, physical location and at-home status remain unverified');
 expect(element.textContent).toContain('Calendar completeness has not been reviewed');expect(element.textContent).toContain('Automatic update check unavailable');
 if(calendar_status==='stored_snapshot') expect(element.textContent).toContain('Snapshot prepared: 2026-10-18 05:00 Pacific');
 else expect(element.textContent).not.toContain('Snapshot prepared:');
});

test('page-wide refresh reaches neural data without resetting an open settings panel',async()=>{
 await mount();await click('Inspect current-left-1');
 await act(async()=>root.render(<HomeNeuralData participant={SYNTHETIC_PARTICIPANT} refreshRevision={3}/>));
 expect(mockProps).toEqual([SYNTHETIC_PARTICIPANT,[3,0],undefined,true]);
 expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
});


test('neural view explicitly identifies shared exact-zero analysis policy while preserving raw and current distinctions',async()=>{
 mockQuery.data.chronic_analysis_policy={id:'prasad_chronic_v1',exact_zero_power_excluded:true,invalid_code_power_excluded:true,raw_values_preserved:true};
 await mount();expect(element.textContent).toContain('excludes exact-zero chronic power');
 expect(element.textContent).toContain('not evidence that zero is physiologically invalid');
 expect(element.textContent).toContain('Raw recordings and zero-current readings are preserved');
});

test.each([undefined,{}, {id:'other'}, {id:'prasad_chronic_v1',exact_zero_power_excluded:false},
 {id:'prasad_chronic_v1',exact_zero_power_excluded:true,invalid_code_power_excluded:false},
 {id:'prasad_chronic_v1',exact_zero_power_excluded:true,invalid_code_power_excluded:true,raw_values_preserved:false}])('does not claim an unsupported analysis policy (%p)',async(policy)=>{
 // This test uses a direct ReactDOM root, whose updates require act.
 // eslint-disable-next-line testing-library/no-unnecessary-act
 await act(async()=>root.render(<NeuralAnalysisPolicy policy={policy}/>));expect(element.textContent).toBe('');
});

test.each(['recorded','unverified'])('settings details surface %s sensing provenance rather than silently endorsing inherited labels',async(status)=>{
 mockQuery.data.windows[0].panels[0].segments[0].sensing_provenance={status,metadata_available:true,conflicting_settings:false,inherited_settings:status==='unverified'};
 await mount();await click('Inspect current-left-1');
 expect(element.textContent).toContain(status==='recorded'?'Sensing labels follow the recorded schedule':'Unverified sensing labels:');
 if(status==='unverified')expect(element.textContent).toContain('inherited without a direct settings record');
});

test('current-only canonical lead remains visible and does not claim all recordings are absent',async()=>{
 const period=window('current');period.panels=[{side:'right',segments:[],amplitude_series:[{time,amplitude:0}],amplitude_provenance:'Lead current at recorded times.'}];
 mockQuery.data.windows=[period];await mount();
 expect(element.textContent).toContain('Recorded lead current is shown; no sensing settings interval');
 expect(element.textContent).toContain('this lead’s recorded current at its own sample times');
 expect(element.textContent).not.toContain('No eligible home recordings for this side');
});

test('operator-confirmed continuity replaces blanket home uncertainty without verifying physical location or sensing settings',async()=>{
 mockQuery.data.observation_windows=[observed('current')];
 mockQuery.data.observation_provenance={calendar_status:'stored_snapshot',home_status:'assumed_continuing_home',home_status_basis:'operator_confirmed_no_new_stimulation_visits',home_status_confirmed_through:'2026-10-20'};
 await mount();
 expect(element.textContent).toContain('study operator confirmed no intervening stimulation visits through 2026-10-20');
 expect(element.textContent).toContain('A clinic sheet or weekly stimulation summary documenting a new session');
 expect(element.textContent).toContain('Physical location is not independently verified');
 expect(element.textContent).toContain('does not establish sensing contacts or a controlling stimulation relationship');
 expect(element.textContent).not.toContain('at-home status remain unverified');
 delete mockQuery.data.observation_provenance.home_status_confirmed_through;await mount();
 expect(element.textContent).toContain('confirmed no intervening stimulation visits.');
 mockQuery.data.observation_provenance.home_status_basis='unknown';await mount();
 expect(element.textContent).toContain('at-home status remain unverified');
 expect(element.textContent).not.toContain('Home period assumed to continue');
 mockQuery.data.observation_provenance={calendar_status:'stored_snapshot',home_status:'assumed_continuing_home',home_status_basis:'documented_stimulation_calendar',home_confirmation_status:'superseded_by_documented_session',last_documented_stimulation_date:'2026-10-22'};
 await mount();expect(element.textContent).toContain('last documented stimulation session was 2026-10-22');
 expect(element.textContent).toContain('supersedes the earlier no-new-visits confirmation');
 expect(element.textContent).not.toContain('at-home status remain unverified');
 delete mockQuery.data.observation_provenance.last_documented_stimulation_date;await mount();
 expect(element.textContent).toContain('the last documented stimulation session;');
});
