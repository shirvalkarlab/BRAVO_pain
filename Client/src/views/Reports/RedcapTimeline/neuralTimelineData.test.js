import {NEURAL_METRICS, quantity, programsAt, parameterValue, knownSegments, neuralPlot} from './neuralTimelineData';

const metric = key => NEURAL_METRICS.find(item => item.key === key);
const time = (day, hour = '12:00:00') => Date.parse(`2025-01-${String(day).padStart(2,'0')}T${hour}-08:00`) / 1000;
const rows = values => Object.entries(values).map(([label,value]) => ({label,value}));
const range = {start:'2025-01-02',end:'2025-01-08'};
const event = (day, left = {}, right = {}, extra = {}) => ({
  id:`synthetic-${day}`,time:time(day),kind:'settings_observed',label:'Group D · Settings observed',
  settings:{group:rows({'Group':'Group D','Mode at observation':'Open loop / fixed stimulation','Cycling':'Off'}),left:rows(left),right:rows(right)},...extra,
});
const parameter = (key, values, group = {}) => parameterValue(metric(key),{rows:values},group);

test('defaults include all requested source settings with explicit physical units',()=>{
  expect(NEURAL_METRICS.map(item=>item.key)).toEqual(['contacts','mode','frequency','amplitude','pulse_width']);
  expect(NEURAL_METRICS.filter(item=>item.unit).map(item=>item.unit)).toEqual(['Hz','mA','µs']);
});

test.each([
  ['0 mA','mA',0],[' +2.5 Hz ','Hz',2.5],['.5 s','s',0.5],['1. µs','µs',1],
  ['90 μs','µs',90],['90 us','µs',90],['3mA','mA',3],['1 s','s',1],
  [undefined,'Hz',null],[null,'mA',null],['Not recorded','Hz',null],['Unknown','mA',null],
  ['2 mA (reviewed note); export: 3 mA','mA',null],['2 Hz','mA',null],['-1 mA','mA',null],
  ['NaN mA','mA',null],['Infinity mA','mA',null],['1e3 Hz','Hz',null],['2 MA','mA',null],
  ['2 mA extra','mA',null],['9'.repeat(400)+' mA','mA',null],[2,'mA',null],
])('numeric parsing requires a whole finite quantity and matching units: %p',(raw,unit,expected)=>{
  expect(quantity(raw,unit)).toBe(expected);
});

test('multi-program labels retain side identity, tablet targets, raw values and controller fields',()=>{
  const source=event(2,{'Program 2 · Tablet target':'GPi','Program 2 · Stimulation contacts':'Case+, 2a−','Program 2 · Sensing source hemisphere':'Right','Program 2 · Frequency':55,'Program 1 · Tablet target':'VIM','Program 1 · Pulse width':null}, {'Frequency':'80 Hz'});
  const before=JSON.stringify(source);
  expect(programsAt(source,'other')).toEqual([
    {id:'left:2',side:'left',label:'L GPi · Program 2',rows:{'Tablet target':'GPi','Stimulation contacts':'Case+, 2a−','Sensing source hemisphere':'Right','Frequency':'55'}},
    {id:'left:1',side:'left',label:'L VIM · Program 1',rows:{'Tablet target':'VIM','Pulse width':''}},
    {id:'right:',side:'right',label:'R lead',rows:{Frequency:'80 Hz'}},
  ]);
  expect(programsAt({},'other')).toEqual([]);
  expect(programsAt({settings:{left:[]}},'other')).toEqual([]);
  expect(JSON.stringify(source)).toBe(before);
});

test('running amplitude is a programmed range; paused amplitude is fixed even with retained limits',()=>{
  const adaptive={'Adaptive state':'Running','Adaptive amplitude range':'0 mA to 3 mA','Paused amplitude':'0 mA','Amplitude':'2 mA'};
  expect(parameter('amplitude',adaptive)).toEqual({low:0,high:3,raw:'0 mA to 3 mA',kind:'range'});
  expect(parameter('amplitude',{'Adaptive state':'Suspended','Adaptive amplitude range':'0 mA to 3 mA','Fixed / paused amplitude':'0 mA','Amplitude':'2 mA'})).toEqual({value:0,raw:'0 mA',kind:'fixed'});
  expect(parameter('amplitude',{'Amplitude':'0 mA'})).toEqual({value:0,raw:'0 mA',kind:'fixed'});
  expect(parameter('frequency',{'Frequency':'55 Hz'})).toEqual({value:55,raw:'55 Hz',kind:'fixed'});
  expect(parameter('pulse_width',{'Pulse width':'90 µs'})).toEqual({value:90,raw:'90 µs',kind:'fixed'});
  expect(parameter('amplitude',{})).toEqual({raw:'Not recorded',kind:'unresolved'});
});

test.each(['3 mA to 2 mA','Not recorded to 3 mA','2 mA to Not recorded','2 mA','2 mA to 3 mA to 4 mA','2 Hz to 3 Hz','2 mA (reviewed note); export: 3 mA'])('unresolved amplitude evidence remains exact: %s',raw=>{
  expect(parameter('amplitude',{'Adaptive state':'Running','Adaptive amplitude range':raw})).toEqual({raw,kind:'unresolved'});
});

test('equal bounds are allowed and conflicts cannot become unqualified numeric points',()=>{
  expect(parameter('amplitude',{'Adaptive state':'Running','Adaptive amplitude range':'2 mA to 2 mA'})).toEqual({low:2,high:2,raw:'2 mA to 2 mA',kind:'range'});
  const raw='2.2 mA (reviewed note); export: 2 mA';
  expect(parameter('amplitude',{'Fixed / paused amplitude':raw})).toEqual({raw,kind:'unresolved'});
});

test('known segments subtract open, closed, overlapping and clipped gaps without bridging',()=>{
  const a='2025-01-02 00:00:00', b='2025-01-08 23:59:59';
  expect(knownSegments(a,b,[])).toEqual([[a,b]]);
  expect(knownSegments(b,a,[])).toEqual([]);
  expect(knownSegments(a,a,[])).toEqual([]);
  expect(knownSegments(a,b,[{start:time(1),end:time(2,'00:00:00')},{start:time(9),end:null}])).toEqual([[a,b]]);
  expect(knownSegments(a,b,[{start:time(3),end:time(5)},{start:time(4),end:time(6)}])).toEqual([[a,'2025-01-03 12:00:00'],['2025-01-06 12:00:00',b]]);
  expect(knownSegments(a,b,[{start:time(1),end:time(3)},{start:time(7),end:null}])).toEqual([['2025-01-03 12:00:00','2025-01-07 12:00:00']]);
  expect(knownSegments(a,b,[{start:time(1),end:time(9)}])).toEqual([]);
});

test('plot window includes preceding context but only marks actual in-window observations',()=>{
  const first=event(1,{Frequency:'10 Hz'}), second=event(4,{Frequency:'20 Hz'}), after=event(10,{Frequency:'30 Hz'});
  const source=[after,second,first,{time:NaN},event(0,{Frequency:'5 Hz'},{},{time:time(1)-86400})];
  const before=JSON.stringify(source);
  const output=neuralPlot(source,metric('frequency'),range,'other');
  expect(output.traces).toHaveLength(2);
  expect(output.traces[0]).toMatchObject({mode:'lines',connectgaps:false,x:['2025-01-02 00:00:00','2025-01-04 12:00:00','2025-01-04 12:00:00','2025-01-08 23:59:59',null],y:[10,10,20,20,null]});
  expect(output.traces[1]).toMatchObject({mode:'markers',x:['2025-01-04 12:00:00'],y:[20],marker:{symbol:['circle']}});
  expect(JSON.stringify(source)).toBe(before);
});

test('unknown gaps blank segments and suppress markers including open-ended gaps',()=>{
  const output=neuralPlot([event(2,{Frequency:'10 Hz'}),event(4,{Frequency:'20 Hz'}),event(6,{Frequency:'30 Hz'})],metric('frequency'),range,'other',[{start:time(3),end:time(5)},{start:time(6),end:null}]);
  expect(output.traces[0].x).toEqual(['2025-01-02 12:00:00','2025-01-03 12:00:00',null,'2025-01-05 12:00:00','2025-01-06 12:00:00',null]);
  expect(output.traces[1].x).toEqual(['2025-01-02 12:00:00']);
  expect(neuralPlot([event(4,{Frequency:'20 Hz'})],metric('frequency'),range,'other',[{start:time(1),end:null}]).traces).toEqual([]);
});

test('range envelopes represent left and right configured bounds with day-precision open markers',()=>{
  const record=event(2,{'Adaptive state':'Running','Adaptive amplitude range':'0 mA to 3 mA'}, {'Adaptive state':'Running','Adaptive amplitude range':'1 mA to 2 mA'}, {time_precision:'day'});
  const output=neuralPlot([record],metric('amplitude'),range,'other');
  expect(output.traces).toHaveLength(8);
  expect(output.traces.filter(trace=>trace.mode==='markers').map(trace=>trace.y)).toEqual([[0],[3],[1],[2]]);
  expect(output.traces[0].line).toMatchObject({dash:'dash',color:'#356E9B'});
  expect(output.traces[4].line.color).toBe('#B16B39');
  expect(output.traces[1].marker.symbol).toEqual(['diamond-open']);
  expect(output.shapes).toEqual([
    expect.objectContaining({x0:'2025-01-02 12:00:00',x1:'2025-01-08 23:59:59',y0:0,y1:3}),
    expect.objectContaining({y0:1,y1:2}),
  ]);
});

test('conflict evidence and hostile source text survive unchanged in records and are escaped in tooltips',()=>{
  const raw='2.2 mA (reviewed note); export: 2 mA';
  const record=event(2,{'Tablet target':'<img>','Stimulation contacts':'Case+, 2a−','Amplitude':raw}, {},{label:'Group <script> & "quoted"',evidence:'<script>unsafe</script>'});
  const before=JSON.stringify(record);
  const unresolved=neuralPlot([record],metric('amplitude'),range,'other');
  expect(unresolved.unresolved).toEqual([{id:record.id,time:'2025-01-02 12:00:00',target:'L <img>',raw}]);
  expect(unresolved.traces).toEqual([]);
  const plotted=neuralPlot([record],metric('contacts'),range,'other');
  const tooltip=plotted.traces[1].customdata[0][1];
  expect(tooltip).toContain('Group &lt;script&gt; &amp; &quot;quoted&quot;');
  expect(tooltip).toContain('L &lt;img&gt;');
  expect(tooltip).not.toContain('<script>');
  expect(tooltip).toContain(raw);
  expect(plotted.traces[0].name).toBe('Contact configurations');
  const numeric=neuralPlot([event(2,{'Tablet target':'<img>',Frequency:'10 Hz'})],metric('frequency'),range,'other');
  expect(numeric.traces[0].name).toBe('L &lt;img&gt;');
  expect(JSON.stringify(record)).toBe(before);
});

test('zero fixed amplitude stays zero and never creates an OFF or sham classification',()=>{
  const record=event(2,{'Adaptive state':'Not configured','Amplitude':'0 mA'});
  expect(neuralPlot([record],metric('amplitude'),range,'other').traces[1].y).toEqual([0]);
  expect(neuralPlot([record],metric('mode'),range,'other').categories).toEqual(['Open loop / fixed · No cycling']);
});

test('adjacent known settings have a vertical connected step at the second observation',()=>{
  const result=neuralPlot([event(2,{Frequency:'10 Hz'}),event(4,{Frequency:'20 Hz'}),event(6,{Frequency:'30 Hz'})],metric('frequency'),range,'other');
  expect(result.traces[0]).toMatchObject({x:['2025-01-02 12:00:00','2025-01-04 12:00:00','2025-01-04 12:00:00','2025-01-06 12:00:00','2025-01-06 12:00:00','2025-01-08 23:59:59',null],y:[10,10,20,20,30,30,null],connectgaps:false,line:{shape:'hv'}});
  expect(result.traces[0].customdata.map(value=>value[0])).toEqual(['synthetic-2','synthetic-2','synthetic-4','synthetic-4','synthetic-6','synthetic-6','']);
});

test.each([{}, {Frequency:'Not recorded'}])('a missing program or missing parameter prevents a bridge through the intervening observation: %p',middle=>{
  const result=neuralPlot([event(2,{Frequency:'10 Hz'}),event(4,middle),event(6,{Frequency:'30 Hz'})],metric('frequency'),range,'other');
  expect(result.traces[0].x).toEqual(['2025-01-02 12:00:00','2025-01-04 12:00:00',null,'2025-01-06 12:00:00','2025-01-08 23:59:59',null]);
  expect(result.traces[0].y).toEqual([10,10,null,30,30,null]);
});

test('mode and cycling produce one shared trace with numerically sorted categories and remapped values',()=>{
  const state=(day,mode,cycle,left={},right={})=>event(day,left,right,{settings:{group:rows({'Mode at observation':mode,Cycling:cycle}),left:rows(left),right:rows(right)}});
  const records=[state(2,'Open loop','On · on 600 s / off 60 s'),state(3,'Closed loop','Off',{'Adaptive state':'Running','Threshold mode':'Dual threshold direct'},{'Adaptive state':'Paused','Threshold mode':'Dual threshold direct'}),state(4,'Open loop','Off'),state(5,'Open loop','On · on 120 s / off 60 s'),state(6,'Open loop','Off')];
  const output=neuralPlot(records,metric('mode'),range,'other');
  expect(output.traces).toHaveLength(2);
  expect(output.categories).toEqual(['Open loop / fixed · No cycling','Open loop / fixed · Cycling on 2 min / off 1 min','Open loop / fixed · Cycling on 10 min / off 1 min','Closed loop · dual threshold']);
  expect(output.traces[1].y).toEqual([2,3,0,1,0]);
  expect(output.traces[0].y).toEqual([2,2,3,3,0,0,1,1,0,0,null]);
  expect(output.traces[0].line.color).toBe('#65519A');
});

test('one paired contact configuration state deduplicates reordered equivalent source contacts',()=>{
  const first=event(2,{'Stimulation contacts':'Case+, 1−'},{'Stimulation contacts':'Case+, 10a−'});
  const second=event(4,{'Stimulation contacts':'1c−, 1a−, Case+, 1b−'},{'Stimulation contacts':'10a−, Case+'});
  const changed=event(6,{'Stimulation contacts':'Case+, 2−'},{'Stimulation contacts':'Case+, 10a−'});
  const result=neuralPlot([first,second,changed],metric('contacts'),range,'RCS08');
  expect(result.categories).toEqual(['C1','C2']);
  expect(result.traces).toHaveLength(2);
  expect(result.traces[1].y).toEqual([0,0,1]);
  expect(result.configurations).toHaveLength(2);
  expect(result.configurations[0].knownGeometry).toBe(true);
  expect(result.configurations[0].leads.map(lead=>lead.side)).toEqual(['left','right']);
  expect(neuralPlot([first],metric('contacts'),range,'other').configurations[0].knownGeometry).toBe(false);
});

test('missing settings remain explicit in categorical plots and empty plots preserve the full return contract',()=>{
  const record={...event(2),settings:undefined};
  expect(neuralPlot([record],metric('mode'),range,'other').categories).toEqual(['Group mode not recorded']);
  expect(neuralPlot([record],metric('contacts'),range,'other').configurations[0].leads).toEqual([]);
  expect(neuralPlot([],metric('mode'),range,'other')).toEqual({traces:[],shapes:[],categories:[],unresolved:[],configurations:[]});
});

test('only the known numeric subset is plotted while an unknown side remains unresolved, never zero',()=>{
  const record=event(2,{'Frequency':'55 Hz'},{'Frequency':'Not recorded'});
  const result=neuralPlot([record],metric('frequency'),range,'other');
  expect(result.traces).toHaveLength(2);
  expect(result.traces[1].y).toEqual([55]);
  expect(result.traces[0].y).toEqual([55,55,null]);
  expect(result.unresolved).toEqual([{id:record.id,time:'2025-01-02 12:00:00',target:'R lead',raw:'Not recorded'}]);
});

test('contact configuration identifiers remain stable when a later date window is selected',()=>{
  const events=[event(1,{'Stimulation contacts':'C+1-'}),event(3,{'Stimulation contacts':'C+2-'}),event(5,{'Stimulation contacts':'C+3-'})];
  const whole=neuralPlot(events,metric('contacts'),{start:'2025-01-01',end:'2025-01-08'},'RCS08');
  const later=neuralPlot(events,metric('contacts'),{start:'2025-01-05',end:'2025-01-08'},'RCS08');
  expect(whole.categories).toEqual(['C1','C2','C3']);expect(later.categories).toEqual(['C2','C3']);expect(later.configurations.map(c=>c.number)).toEqual([2,3]);
});
