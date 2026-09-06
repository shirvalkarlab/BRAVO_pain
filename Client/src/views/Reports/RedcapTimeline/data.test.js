import {DEFAULT_METRICS, localTime, fullRange, filterPoints, rollingMedian, metricTraces, stageShapes, past28Range, transitionLayout, calendarTicks, settingsSummary, eventTimeLabel, homeTiming, unknownIntervalsInRange} from './data';

const point=(day,value,phase='pre',extra={})=>({time:Date.parse(`${day}T12:00:00-08:00`)/1000,value,phase,source:'Reviewed form',record:'synthetic',...extra});
const phases=[{key:'pre',label:'Pre-trial',color:'#111111',start:point('2025-01-01',0).time},
  {key:'stage1',label:'Stage 1',color:'#222222',start:point('2025-07-16',0).time}];
const range={start:'2025-01-01',end:'2025-12-31'};

test('the eleven requested defaults retain user order and the standard MPQ scale',()=>{
  expect(DEFAULT_METRICS).toEqual(['mood_vas','nrs_intensity','vas_intensity','left_leg_vas_intensity','back_vas_intensity','mpq_sens','mpq_aff','mpq_standard_0_45','firey','tingly','electrocuting']);
  expect(new Set(DEFAULT_METRICS).size).toBe(11);
});

test('Pacific timestamps respect day boundaries and both daylight-saving transitions',()=>{
  expect(localTime(Date.parse('2025-01-02T07:59:59Z')/1000)).toBe('2025-01-01 23:59:59');
  expect(localTime(Date.parse('2025-01-02T08:00:00Z')/1000)).toBe('2025-01-02 00:00:00');
  expect(localTime(Date.parse('2025-03-09T09:59:59Z')/1000)).toBe('2025-03-09 01:59:59');
  expect(localTime(Date.parse('2025-03-09T10:00:00Z')/1000)).toBe('2025-03-09 03:00:00');
  expect(localTime(Date.parse('2025-11-02T08:30:00Z')/1000)).toBe('2025-11-02 01:30:00');
  expect(localTime(Date.parse('2025-11-02T09:30:00Z')/1000)).toBe('2025-11-02 01:30:00');
});

test('full range starts at the earliest observation but extends to the actual Pacific day, including empty histories',()=>{
  const now=Date.parse('2026-09-04T06:59:59Z');
  const metrics=[{points:[point('2025-07-17',8)]},{points:[point('2024-12-12',3),point('2026-08-01',5)]}];
  expect(fullRange(metrics,now)).toEqual({start:'2024-12-12',end:'2026-09-03'});
  expect(fullRange([],now)).toEqual({start:'2026-09-03',end:'2026-09-03'});
  const clock=jest.spyOn(Date,'now').mockReturnValue(now);
  expect(fullRange([{points:[]}])).toEqual({start:'2026-09-03',end:'2026-09-03'});
  clock.mockRestore();
});

test('date filtering is inclusive on Pacific calendar dates, preserves real zeros and never adds observations',()=>{
  const points=[point('2025-01-01',99),point('2025-01-02',0),point('2025-01-03',10),point('2025-01-04',20)];
  expect(filterPoints(points,'2025-01-02','2025-01-03')).toEqual(points.slice(1,3));
  expect(filterPoints(points,'2025-01-04','2025-01-02')).toEqual([]);
  expect(filterPoints([],'2025-01-01','2025-12-31')).toEqual([]);
});

// Independently checked against pandas Series.rolling(5, min_periods=1,
// center=True).median() in the notebook's own Python environment.
test.each([
  [[],[]],
  [[7],[7]],
  [[7,1],[4,4]],
  [[9,1,3],[3,3,3]],
  [[9,1,3,7],[3,5,5,3]],
  [[9,1,3,7,5],[3,5,5,4,5]],
  [[9,1,3,7,5,11],[3,5,5,5,6,7]],
])('continuous centered five-survey median matches pandas edge windows for %p',(values,expected)=>{
  const points=values.map((value,i)=>point(`2025-01-0${i+1}`,value));
  expect(rollingMedian(points).map(p=>p.value)).toEqual(expected);
  expect(points.map(p=>p.value)).toEqual(values);
});

test('median sorts by time and continues across phase changes and long gaps',()=>{
  const points=[point('2025-01-01',2),point('2025-01-06',4),point('2025-01-12',90),point('2025-01-13',10,'stage1')];
  const output=rollingMedian([...points].reverse());
  expect(output.map(p=>p?.value??null)).toEqual([4,7,7,10]);
  expect(output.filter(Boolean).map(p=>p.time)).toEqual(points.map(p=>p.time));
});

test('continuous median does not insert artificial missing points across unobserved days',()=>{
  const points=[point('2025-01-01',0),point('2025-01-02',10),point('2025-01-04',20)];
  expect(rollingMedian(points).map(p=>p?.value??null)).toEqual([10,10,10]);
});

test('observed tooltips show score, time and home context without form/record clutter',()=>{
  const metric={label:'Mood <img onerror="bad">',points:[point('2025-01-01',0),point('2025-01-02',10,'unknown')]};
  const [observed]=metricTraces(metric,phases,range,false);
  expect(observed).toMatchObject({type:'scatter',mode:'markers',y:[0,10],marker:{color:['#111111','#777777']}});
  expect(observed.customdata).toEqual(['Pre-trial<br>Home program context<br>Home settings not established','<br>Home program context<br>Home settings not established']);
  expect(observed.hovertemplate).toContain('Pacific');expect(observed.hovertemplate).not.toMatch(/Form:|Record:/);
  expect(observed.hovertemplate).toContain('Mood &lt;img onerror=&quot;bad&quot;&gt;');expect(observed.hovertemplate).not.toContain('<img');
});

test('date filtering preserves full-series medians and continuous connecting segments',()=>{
  const metric={label:'Pain',points:[point('2025-01-01',0),point('2025-01-02',10),point('2025-01-04',20),point('2025-01-10',100)]};
  const [observed,trend]=metricTraces(metric,phases,{start:'2025-01-02',end:'2025-01-04'},true);
  expect(observed.y).toEqual([10,20]);expect(trend.y).toEqual([15,15]);
  expect(trend.x).toEqual(['2025-01-02 12:00:00','2025-01-04 12:00:00']);expect(trend).toMatchObject({mode:'lines',connectgaps:true});
  expect(metricTraces({label:'Empty',points:[]},[],range,true).map(t=>t.y)).toEqual([[],[]]);
});

test('stage lines are drawn only for boundaries inside the selected window, with paper-relative full height',()=>{
  const shapes=stageShapes(phases,{start:'2025-01-01',end:'2025-07-16'});
  expect(shapes).toEqual([{type:'line',xref:'x',yref:'paper',x0:'2025-07-16 13:00:00',x1:'2025-07-16 13:00:00',y0:0,y1:1,line:{color:'#222222',width:1.5,dash:'dash'},layer:'below'}]);
  expect(stageShapes(phases,{start:'2025-01-02',end:'2025-07-15'})).toEqual([]);
});

test.each([
  ['2025-03-20','2025-02-21'], // Spring daylight-saving change.
  ['2025-11-10','2025-10-14'], // Autumn daylight-saving change.
  ['2024-03-10','2024-02-12'], // Leap day.
  ['2026-01-10','2025-12-14'],
])('past 28 days includes today and exactly 27 earlier calendar days (%s)',(today,start)=>{
  expect(past28Range(today)).toEqual({start,end:today});
  expect((Date.parse(today)-Date.parse(start))/86400000+1).toBe(28);
});

test('QC-valid visit scores contribute to the display median even while X markers are hidden',()=>{
  const metric={label:'Pain <script>',points:[point('2025-01-01',0),point('2025-01-03',10),point('2025-01-05',20)]};
  const visits=[point('2025-01-02',99),point('2025-01-04',100)];
  const contextual=metricTraces(metric,phases,range,true,visits);
  const hidden=metricTraces(metric,phases,range,true,visits,[],false);
  expect(contextual.slice(0,2)).toEqual(hidden);
  expect(contextual[0].y).toEqual([0,10,20]);expect(contextual[1].y).toEqual([10,54.5,20,59.5,20]);
  expect(contextual[2]).toMatchObject({mode:'markers',y:[99,100],marker:{symbol:'x'}});
  expect(contextual[2].customdata[0]).toContain('Home program context; clinic testing may differ');
  expect(contextual[1].customdata[1]).toContain('Visit day');
  expect(contextual[2].hovertemplate).toContain('Pain &lt;script&gt;');expect(contextual[2].name).not.toContain('excluded');
  expect(metricTraces(metric,phases,range,false,visits)).toHaveLength(2);
  expect(metricTraces(metric,phases,range,false,[point('2026-01-01',100)])).toHaveLength(1);
  expect(metric.points.map(p=>p.value)).toEqual([0,10,20]);
});

test('transition red lines carry escaped selectable labels/evidence and stagger crowded annotations',()=>{
  const events=Array.from({length:4},(_,i)=>({id:`transition-${i}`,number:i+1,time:point(`2025-01-0${i+1}`,0).time,label:'Group <B> "test"',evidence:'Observed <img> & not onset'}));
  const layout=transitionLayout(events);
  expect(layout.shapes).toHaveLength(4);
  expect(layout.shapes[0]).toMatchObject({type:'line',x0:'2025-01-01 12:00:00',x1:'2025-01-01 12:00:00',y0:0,y1:1,line:{color:'#C62828',dash:'dash'},layer:'below'});
  expect(layout.annotations.map(a=>a.y)).toEqual([1.08,1.23,1.3800000000000001,1.08]);
  expect(layout.annotations[0]).toMatchObject({name:'transition-0',text:'1. Group &lt;B&gt; &quot;test&quot;',hovertext:'Home settings not established<br>Observed &lt;img&gt; &amp; not onset<br>Click for complete settings',captureevents:true,showarrow:false});
  expect(transitionLayout([])).toEqual({shapes:[],annotations:[]});
});

test('snapshot annotation shows compact group and mode while full evidence remains in its tooltip',()=>{
  const events=[{id:'normal',number:1,time:point('2025-01-01',0).time,kind:'settings_observed',label:'Group A · Open loop · Settings observed',evidence:'Observed not onset'},
    {id:'malicious',number:2,time:point('2025-01-02',0).time,kind:'settings_observed',label:'<Group> · "mode" & unknown · Settings observed',evidence:'<unsafe>'},
    {id:'single',number:3,time:point('2025-01-03',0).time,kind:'settings_observed',label:'Group only',evidence:'Unknown'},
    {id:'long',number:4,time:point('2025-01-04',0).time,kind:'group_change',label:'A very long device change log description beyond annotation width',evidence:'Recorded'}];
  const {annotations}=transitionLayout(events);
  expect(annotations[0].text).toBe('1. Group A<br>Open loop');
  expect(annotations[0].hovertext).not.toContain('Observed not onset');
  expect(annotations[1].text).toBe('2. &lt;Group&gt;<br>&quot;mode&quot; &amp; unknown');
  expect(annotations[1].hovertext).toContain('Home settings not established');
  expect(annotations[2].text).toBe('3. Group only');
  expect(annotations[3].text).toBe('4. A very long device change l…');
  expect(annotations[3].hovertext).toContain('Recorded');
});

const row=(label,value)=>({label,value});
const completeSettings={group:[row('Group','Group A'),row('Mode at observation','Open loop'),row('Stimulation status','On'),row('High-pass filter','0.85 Hz'),row('Sensing blanking','2500 µs'),row('Cycling','On · on 10 s / off 5 s'),row('SoftStart/Stop','On · 2 s')],
  left:[row('Adaptive state','Running'),row('Stimulation contacts','Case+, 2−'),row('Frequency','55 Hz'),row('Amplitude','3.5 mA'),row('Pulse width','100 µs'),row('Sensing source hemisphere','Left'),row('Sensing contacts','0–2'),row('Biomarker center frequency','8 Hz'),row('Averaging duration','1000 ms'),row('Lower LFP threshold','50 LFP Power (LSB)'),row('Upper LFP threshold','100 LFP Power (LSB)'),row('Lower onset duration','200 ms'),row('Upper onset duration','300 ms'),row('Detection blanking duration','400 ms'),row('Adaptive startup delay','500 ms'),row('Transition up','600 ms'),row('Transition down','700 ms'),row('Program 2 · Frequency','130 Hz')],
  right:[row('Stimulation contacts','Case+, 10−'),row('Frequency','55 Hz'),row('Fixed / paused amplitude','2 mA'),row('Adaptive amplitude range','1 mA to 4 mA'),row('Pulse width','90 µs'),row('Sensing source hemisphere','Left'),row('Sensing contacts','0–2'),row('Biomarker center frequency','8 Hz'),row('Lower LFP threshold','50 LFP Power (LSB)'),row('Upper LFP threshold','110 LFP Power (LSB)')]};

test('concise settings include true units, all controller/timing fields and shared sensing without fabricating duplicate controllers',()=>{
  const summary=settingsSummary(completeSettings);
  expect(summary).toContain('L C+2−<br>55 Hz · 3.5 mA · 100 µs');
  expect(summary).toContain('R C+10−<br>55 Hz · paused 2 mA · range 1 mA to 4 mA · 90 µs');
  expect(summary).toContain('HPF: 0.85 Hz · Blanking: 2500 µs · Cycling: On · on 10 s / off 5 s');
  expect(summary).toContain('SoftStart/Stop: On · 2 s');
  expect(summary).toContain('Shared sensing: Source: Left · Contacts: 0–2 · Center: 8 Hz');
  expect(summary.match(/Lower threshold: 50 LFP Power \(LSB\)/g)).toHaveLength(1);
  expect(summary).toContain('Upper threshold: 100 LFP Power (LSB)');expect(summary).toContain('Stored upper threshold (not controlling stimulation): 110 LFP Power (LSB)');
  for (const value of ['1000 ms','200 ms','300 ms','400 ms','500 ms','600 ms','700 ms','Program 2 · Frequency: 130 Hz']) expect(summary).toContain(value);
  expect(settingsSummary()).toBe('Home settings not established');
  expect(settingsSummary({})).toBe('L: Settings not recorded<br>R: Settings not recorded');
});

test('unknown or distinct sensing sources remain separate and all source-derived settings text is escaped',()=>{
  const left=[row('Sensing source hemisphere','Not recorded'),row('Sensing contacts','<pair> "x" & y'),row('Custom field',"'unsafe'")];
  const right=[row('Sensing source hemisphere','Not recorded'),row('Sensing contacts','<pair> "x" & y')];
  expect(settingsSummary({left,right})).not.toContain('Shared sensing');
  expect(settingsSummary({left,right})).toContain('&lt;pair&gt; &quot;x&quot; &amp; y');
  expect(settingsSummary({left,right})).toContain('&#39;unsafe&#39;');
  expect(settingsSummary({left:[row('Sensing source hemisphere','Left')],right:[row('Sensing source hemisphere','Right')]})).not.toContain('Shared sensing');
  expect(settingsSummary({left:[row('Sensing source hemisphere','Left')]})).toContain('R: Settings not recorded');
});

test('point tooltips use only the latest home transition at or before each exact time, independently of chart range',()=>{
  const metric={label:'NRS',points:[point('2025-01-01',1),point('2025-01-02',2),point('2025-01-03',3),point('2025-01-04',4)]};
  const homes=[{time:point('2025-01-03',0).time,settings:{group:[row('Group','Group B')]}},{time:point('2025-01-02',0).time,settings:completeSettings}];
  const [observed]=metricTraces(metric,phases,range,false,[],homes);
  expect(observed.customdata[0]).toContain('Home settings not established');
  expect(observed.customdata[1]).toContain('Group: Group A');expect(observed.customdata[2]).toContain('Group: Group B');expect(observed.customdata[3]).toContain('Group: Group B');
  const zoomed=metricTraces(metric,phases,{start:'2025-01-04',end:'2025-01-04'},false,[],homes)[0];
  expect(zoomed.customdata).toEqual([observed.customdata[3]]);
  const layout=transitionLayout([{id:'home',number:1,time:homes[1].time,label:'Group A',settings:completeSettings,evidence:'Avoid clutter'}]);
  expect(layout.annotations[0].hovertext).toContain('L C+2−<br>55 Hz · 3.5 mA · 100 µs');expect(layout.annotations[0].hovertext).toContain('Avoid clutter');
});

test.each(['2025-03-20','2025-11-10'])('28-day axes label every local calendar day across DST (%s)',today=>{
  const window=past28Range(today);const ticks=calendarTicks(window);
  expect(ticks.tickmode).toBe('array');expect(ticks.tickvals).toHaveLength(28);expect(new Set(ticks.tickvals).size).toBe(28);
  expect(ticks.tickvals[0]).toBe(window.start);expect(ticks.tickvals[27]).toBe(today);
  expect(ticks.ticktext[27]).toBe(today==='2025-03-20'?'3/20':'11/10');expect(ticks.tickangle).toBe(-45);
  expect(calendarTicks({start:'2025-01-01',end:'2025-12-31'})).toEqual({});
});

test('day-precision home changes never imply a midnight activation and same-day surveys carry explicit uncertainty',()=>{
  const event={id:'threshold',time:Date.parse('2026-09-03T07:00:00Z')/1000,time_precision:'day',settings:{group:[row('Group','Group A')],left:[row('Lower LFP threshold','166 LFP Power (LSB)')]}};
  expect(eventTimeLabel(event)).toBe('2026-09-03 · time not recorded');
  expect(homeTiming(event)).toContain('Exact change time is not recorded');
  const metric={label:'NRS',points:[point('2026-09-02',1),point('2026-09-03',2),point('2026-09-04',3)]};
  const trace=metricTraces(metric,[],{start:'2026-09-02',end:'2026-09-04'},false,[],[event])[0];
  expect(trace.customdata[0]).toContain('Home settings not established');
  expect(trace.customdata[1]).toContain('166 LFP Power (LSB)');expect(trace.customdata[1]).toContain('Settings changed this day; survey may precede change');
  expect(trace.customdata[1]).not.toContain('00:00:00');expect(trace.customdata[2]).not.toContain('survey may precede change');
  const observed={...event,time_precision:'second',kind:'settings_observed'};
  expect(eventTimeLabel(observed)).toBe('2026-09-03 00:00:00 Pacific');
  expect(homeTiming(observed)).toContain('activation time not established');
  expect(homeTiming({time:event.time,evidence:'Documented change <exact>'})).toBe('Documented change &lt;exact&gt;');
});

test('unknown home intervals override prior settings at inclusive start and stop at exclusive end without changing scores',()=>{
  const start=point('2025-05-27',0).time,end=point('2025-05-28',0).time;
  const points=[start-1,start,end-1,end].map((time,i)=>({time,value:i}));
  const metric={label:'NRS',points};
  const homes=[{time:start-86400,settings:completeSettings}];
  const intervals=[{start,end,reason:'Missing visit <Final> & conflicting settings'}];
  const normal=metricTraces(metric,[],range,true,[],homes);
  const unknown=metricTraces(metric,[],range,true,[],homes,false,intervals);
  expect(unknown[0].customdata[0]).toContain('Group: Group A');
  for (const index of [1,2]) {
    expect(unknown[0].customdata[index]).toContain('Home settings not established for this interval');
    expect(unknown[0].customdata[index]).toContain('Missing visit &lt;Final&gt; &amp; conflicting settings');
    expect(unknown[0].customdata[index]).not.toContain('3.5 mA');
    expect(unknown[1].customdata[index]).toContain('Home settings not established for this interval');
  }
  expect(unknown[0].customdata[3]).toContain('Group: Group A');
  expect(unknown[0].y).toEqual(normal[0].y);expect(unknown[1].y).toEqual(normal[1].y);
  const visit=metricTraces({label:'NRS',points:[]},[],range,false,[{time:end+86400,value:7}],homes,true,[{start,end:null,reason:'No confirming home snapshot'}]);
  expect(visit[1].customdata[0]).toContain('Visit day');expect(visit[1].customdata[0]).toContain('No confirming home snapshot');expect(visit[1].customdata[0]).not.toContain('3.5 mA');
});

test('uncertainty notices apply only to windows overlapping a gap, including open ends and midnight exclusive bounds',()=>{
  const midnight=Date.parse('2025-05-28T07:00:00Z')/1000;
  const closed={start:midnight-86400,end:midnight,reason:'Missing visit'};
  const open={start:midnight+86400,end:null,reason:'Ongoing gap'};
  expect(unknownIntervalsInRange([closed,open],{start:'2025-05-27',end:'2025-05-27'})).toEqual([closed]);
  expect(unknownIntervalsInRange([closed,open],{start:'2025-05-28',end:'2025-05-28'})).toEqual([]);
  expect(unknownIntervalsInRange([closed,open],{start:'2025-05-29',end:'2026-09-03'})).toEqual([open]);
  expect(unknownIntervalsInRange([],{start:'2025-01-01',end:'2026-09-03'})).toEqual([]);
});


test('inactive adaptive thresholds are explicitly stored values and source rows stay unchanged',()=>{
  const settings={left:[row('Adaptive state','Not configured'),row('Lower LFP threshold','20 LSB'),row('Upper LFP threshold','30 LSB')],right:[row('Adaptive state','Running'),row('Lower LFP threshold','100 LSB')]};
  const before=JSON.stringify(settings);const summary=settingsSummary(settings);
  expect(summary).toContain('Stored lower threshold (not controlling stimulation): 20 LSB');
  expect(summary).toContain('Stored upper threshold (not controlling stimulation): 30 LSB');
  expect(summary).toContain('R: Adaptive state: Running · Lower threshold: 100 LSB');expect(JSON.stringify(settings)).toBe(before);
  const shared={left:[row('Sensing source hemisphere','Left'),...settings.left],right:[row('Sensing source hemisphere','Left'),...settings.left]};
  expect(settingsSummary(shared)).toContain('Shared sensing: Source: Left · Stored lower threshold (not controlling stimulation): 20 LSB');
});


test('RCS08 hover settings use reviewed anatomy, compact stimulation lines and the actual sensing source',()=>{
  const settings={group:[],left:[row('Tablet target','GPi'),row('Stimulation contacts','Case+, 2−'),row('Frequency','55 Hz'),row('Amplitude','3.5 mA'),row('Pulse width','100 µs'),row('Threshold mode','DUAL_THRESHOLD'),row('Sensing source hemisphere','Right'),row('Sensing contacts','9–11')],right:[row('Tablet target','VIM'),row('Stimulation contacts','Case+, 10−')]};
  const before=JSON.stringify(settings);
  const summary=settingsSummary(settings,'RCS08');
  expect(summary).toContain('L GPe C+2−<br>55 Hz · 3.5 mA · 100 µs');
  expect(summary).toContain('R MD Thal C+10−');
  expect(summary).toContain('Threshold mode: Dual threshold');
  expect(summary).toContain('Source: R MD Thal · Contacts: 9–11');
  expect(summary).not.toMatch(/GPi|VIM/);
  expect(settingsSummary(settings,'RCS09')).toContain('L GPi C+2−');
  expect(settingsSummary({left:[row('Tablet target','Left STN'),row('Frequency','130 Hz')]},'RCS09')).toContain('L STN Contacts not recorded<br>130 Hz');
  expect(settingsSummary({left:[row('Threshold mode','unrecorded')]},'RCS08')).toContain('Threshold mode: unrecorded');
  expect(settingsSummary({left:[row('Stimulation contacts','Case+, 2−')]},'RCS08')).toContain('L GPe C+2−');
  expect(JSON.stringify(settings)).toBe(before);
});

test('the live participant route reaches observed, median and transition tooltips without changing survey data',()=>{
  const previous=window.location.pathname;
  window.history.replaceState({},'', '/reports/redcap-pretrial/81b245ec31594d9894f1dfc9438b6348');
  try {
    const metric={label:'Pain',points:[point('2025-01-02',0),point('2025-01-03',8)]};
    const home={time:point('2025-01-01',0).time,id:'raw-home-id',number:1,label:'Group A',settings:completeSettings};
    const traces=metricTraces(metric,phases,range,true,[],[home]);
    expect(traces[0].customdata[0]).toContain('L GPe C+2−<br>55 Hz · 3.5 mA · 100 µs');
    expect(traces[1].customdata[0]).toContain('R MD Thal C+10−');
    expect(transitionLayout([home]).annotations[0]).toMatchObject({name:'raw-home-id'});
    expect(transitionLayout([home]).annotations[0].hovertext).toContain('Shared sensing: Source: L GPe');
    expect(traces[0].y).toEqual([0,8]);expect(traces[1].y).toEqual([4,4]);
    expect(home.settings.left[5].value).toBe('Left');
  } finally { window.history.replaceState({},'',previous); }
});
