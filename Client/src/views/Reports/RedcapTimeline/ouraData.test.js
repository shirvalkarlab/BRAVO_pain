import {OURA_DEFAULTS,ouraPoints,ouraRange,dailySeries,fivePointMedian,visiblePhases,ouraTraces,sampleSeries,sampleTraces} from './ouraData';
const point=(day,value)=>({day,value});
const phase=(key,day,color)=>({key,label:key,color,start:Date.parse(`${day}T08:00:00Z`)/1000});
const phases=[phase('Pre-trial','2026-01-01','#aaa'),phase('Stage 1','2026-06-01','#bbb'),phase('Stage 2','2026-08-15','#ccc'),phase('Future','2027-01-01','#ddd')];

test('approved defaults stay ordered and full history includes only finite observations through supplied Pacific today',()=>{
  expect(OURA_DEFAULTS).toEqual(['steps','heart_rate','hrv','total_calories','sleep_duration','sleep_total']);
  const metrics=[{points:[point('2025-01-01',NaN),point('2026-08-02',3)]},{points:[point('2026-03-01',0),point('2026-06-01',Infinity)]}];
  expect(ouraRange(metrics,'2026-09-03')).toEqual({start:'2026-03-01',end:'2026-09-03'});
  expect(ouraRange([],'2026-09-03')).toEqual({start:'2026-09-03',end:'2026-09-03'});
  const points=[point('2026-08-01',1),point('2026-08-02',0),point('2026-08-03',NaN),point('2026-08-04',null),point('2026-08-05',5),point('2026-08-06',6)];
  expect(ouraPoints(points,{start:'2026-08-02',end:'2026-08-05'})).toEqual([points[1],points[4]]);
});

test('daily line gaps are explicit across missing, excluded, leap and month-boundary days without mutating input',()=>{
  const input=[point('2024-03-02',3),point('2024-02-28',1),point('2024-02-29',2)],before=JSON.stringify(input);
  expect(dailySeries(input)).toEqual([input[1],input[2],point('2024-03-01',null),input[0]]);
  expect(dailySeries([])).toEqual([]);expect(JSON.stringify(input)).toBe(before);
  expect(dailySeries([point('2026-01-01',1),point('2026-03-01',3)])).toEqual([point('2026-01-01',1),point('2026-01-02',null),point('2026-03-01',3)]);
});

test('five-point median uses centered observed values across missing days, excludes nulls and preserves source',()=>{
  const input=[point('2026-08-15',50),point('2026-08-01',999),point('2026-08-08',0),point('2026-08-09',2),point('2026-08-14',10),point('2026-08-10',null)],before=JSON.stringify(input);
  expect(fivePointMedian(input).map(p=>p.value)).toEqual([2,6,10,6,10]);
  expect(fivePointMedian([])).toEqual([]);expect(JSON.stringify(input)).toBe(before);
});

test('phase context keeps the phase already active at the range start, includes intersecting transitions, and excludes future phases',()=>{
  const reversed=[...phases].reverse(),before=JSON.stringify(reversed);
  expect(visiblePhases(reversed,{start:'2026-08-07',end:'2026-09-03'}).map(p=>p.key)).toEqual(['Stage 1','Stage 2']);
  expect(visiblePhases(phases,{start:'2026-08-15',end:'2026-09-03'}).map(p=>p.key)).toEqual(['Stage 2']);
  expect(visiblePhases(phases,{start:'2025-01-01',end:'2025-12-31'})).toEqual([]);
  expect(visiblePhases(phases,{start:'2027-01-02',end:'2027-01-03'}).map(p=>p.key)).toEqual(['Future']);
  expect(visiblePhases([],{start:'2026-01-01',end:'2026-09-03'})).toEqual([]);expect(JSON.stringify(reversed)).toBe(before);
  const pacificBoundary=[{...phases[0],start:Date.parse('2026-08-15T06:30:00Z')/1000}];
  expect(visiblePhases(pacificBoundary,{start:'2026-08-14',end:'2026-08-14'})).toEqual(pacificBoundary);
});

test('observed and median traces retain units, escaped labels, gap breaks and prior-window context without extending the selected dates',()=>{
  const metric={key:'sleep_hrv',label:'HRV <sleep>',unit:'ms & units',points:[point('2026-08-09',2),point('2026-08-14',10),point('2026-08-15',NaN),point('2026-08-16',20)]};
  const range={start:'2026-08-14',end:'2026-08-16'},usedPhases=visiblePhases(phases,range);
  const [observed,median]=ouraTraces(metric,range,usedPhases,true,true);
  expect(observed).toMatchObject({mode:'markers',connectgaps:false,x:['2026-08-14','2026-08-15','2026-08-16'],y:[10,null,20]});
  expect(median).toMatchObject({mode:'lines',connectgaps:false,y:[10,null,10],name:'5-point rolling median'});
  expect(observed.marker.color).toEqual(['#bbb','#ccc','#ccc']);
  expect(observed.customdata[0]).toContain('Stage 1'); expect(observed.customdata[0]).toContain('Daily summary');
  expect(median.customdata[0]).toContain('five observed daily values');
  expect(observed.hovertemplate).toContain('HRV &lt;sleep&gt;');expect(observed.hovertemplate).toContain('ms &amp; units');
  expect(median.hovertemplate).toContain('Rolling median');
  const simple=ouraTraces(metric,range,[],false,false);
  expect(simple).toHaveLength(1);expect(simple[0].mode).toBe('markers');expect(simple[0].marker.color).toEqual(['#356E9B','#356E9B','#356E9B']);expect(simple[0].customdata.every(text=>text.includes('Daily summary'))).toBe(true);
  expect(ouraTraces({...metric,points:[]},range,[],true,false).map(trace=>trace.y)).toEqual([[],[]]);
});

const sample=(iso,value,source='Recorded')=>({time:Date.parse(iso)/1000,day:iso.slice(0,10),value,source});
test('timestamp series includes all intra-day samples and explicit nulls, inserts long-interval gaps, and filters by Pacific date',()=>{
  const first={...sample('2026-08-02T06:59:00Z',1),day:'2026-08-01'},next=sample('2026-08-02T07:00:00Z',0),missing=sample('2026-08-02T07:05:00Z',null),last=sample('2026-08-02T07:20:00Z',20);
  const input=[last,{time:NaN,value:99},missing,next,first],before=JSON.stringify(input),range={start:'2026-08-02',end:'2026-08-02'};
  expect(sampleSeries(input,range)).toEqual([next,missing,{time:missing.time+1,value:null},last]);
  expect(sampleSeries(input,{start:'2026-08-01',end:'2026-08-01'})).toEqual([first]);
  expect(sampleSeries([{time:first.time,value:1}],{start:'2026-08-01',end:'2026-08-01'})).toEqual([{time:first.time,value:1}]);
  expect(sampleSeries([next,sample('2026-08-02T07:10:00Z',Infinity)],range,600).map(p=>p.value)).toEqual([0,null]);
  expect(sampleSeries([next,missing],range,60)).toHaveLength(3);
  expect(sampleSeries([],range)).toEqual([]);expect(JSON.stringify(input)).toBe(before);
});

test('HR and HRV retain every timed reading, exact units and source labels; the five-point median preserves raw samples',()=>{
  const points=[sample('2026-08-02T18:00:00Z',60,'Awake <source>'),sample('2026-08-02T18:05:00Z',null),sample('2026-08-02T18:10:00Z',75,'Sleep & source')];
  const metric={key:'heart_rate',label:'Heart rate <all>',unit:'bpm',resolution:'sample',max_gap_seconds:600,points};
  const range={start:'2026-08-02',end:'2026-08-02'},phases=[{key:'phase',label:'Stage <2>',start:points[2].time,color:'#fff'}];
  const raw=ouraTraces(metric,range,phases,false,true),withDailyMedian=ouraTraces(metric,range,phases,true,true);
  expect(withDailyMedian).toHaveLength(2);expect(withDailyMedian[0]).toEqual(raw[0]);expect(withDailyMedian[1].y).toEqual([67.5,null,67.5]);expect(raw).toHaveLength(1);
  expect(raw[0]).toMatchObject({type:'scattergl',mode:'markers',connectgaps:false,x:['2026-08-02 11:00:00','2026-08-02 11:05:00','2026-08-02 11:10:00'],y:[60,null,75]});
  expect(raw[0].customdata).toEqual([['','Awake &lt;source&gt;','Home settings not established'],['','Recorded',''],['Stage &lt;2&gt;','Sleep &amp; source','Home settings not established']]);
  expect(raw[0].hovertemplate).toContain('bpm');expect(raw[0].hovertemplate).toContain('Heart rate &lt;all&gt;');expect(raw[0].hovertemplate).toContain('Pacific');
  const hrv=sampleTraces({...metric,key:'hrv',label:'HRV',unit:'ms',points:[{time:points[0].time,value:50},{time:points[2].time+900,value:80}]},range,[],false);
  expect(hrv[0].mode).toBe('markers');expect(hrv[0].y).toEqual([50,null,80]);expect(hrv[0].customdata).toEqual([['','','Home settings not established'],['','',''],['','','Home settings not established']]);expect(hrv[0].hovertemplate).toContain('ms');
});

 test('timed settings respect prior records, unknown intervals, and day-precision uncertainty without altering values',()=>{
  const time=Date.parse('2026-08-02T18:00:00Z')/1000;
  const metric={key:'heart_rate',label:'Heart rate',unit:'bpm',resolution:'sample',points:[{time:time-600,day:'2026-08-02',value:55},{time,day:'2026-08-02',value:60},{time:time+600,day:'2026-08-02',value:65}]};
  const homes=[{id:'home',time:time-300,time_precision:'day',settings:{group:[],left:[],right:[]}}];
  const unknown=[{start:time+600,end:null,reason:'Reviewed <gap>'}];
  const traces=ouraTraces(metric,{start:'2026-08-02',end:'2026-08-02'},[],false,true,homes,unknown);
  expect(traces[0].y).toEqual([55,60,65]);
  expect(traces[0].customdata[0][2]).toBe('Home settings not established');
  expect(traces[0].customdata[1][2]).toContain('reading may precede change');
  expect(traces[0].customdata[2][2]).toContain('Reviewed &lt;gap&gt;');
});
