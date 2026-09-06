import {surveyCount,stimulationSettingLines,stimulationSummary,stimulationDetailRows,finalizedProgram,stimulationAxisSettings,comparisonCoverage,compactLabel,topPrograms,conditionSummary,conditionPlot,medicationTimeline,stimulationPlot,medicationConditionPlot,orderedMedicationConditions} from './comparisonData';
const time=day=>Date.parse(`${day}T19:00:00Z`)/1000;
const points=values=>values.map((value,i)=>({time:time('2026-08-01')+i*86400,value}));
const condition=(id,median,count=5)=>({id,label:`Program ${id}`,mode:'open_loop',median,count,points:points(Array.from({length:count},()=>median))});

test('source coverage reports the matching snapshot date and unmatched exclusions without claiming freshness',()=>{
  const text=comparisonCoverage({source_max_survey:time('2026-08-01'),matched:12,canonical_rows:15,unmatched_canonical:3});
  expect(text).toContain('Matching source contains surveys through 2026-08-01 12:00:00 Pacific');
  expect(text).toContain('Matched 12 of 15 reviewed surveys; 3 unmatched surveys are excluded');
  expect(text).not.toMatch(/latest|current|up.to.date/i);
  expect(comparisonCoverage()).toBe('Source coverage details are not available.');
  expect(comparisonCoverage({canonical_rows:15},true)).toBe('Source coverage details are not available.');
  expect(comparisonCoverage({matched:12})).toBe('Source coverage details are not available.');
});

test('medication coverage distinguishes source rows, reviewed survey coverage and incomplete intervals including zero',()=>{
  const text=comparisonCoverage({source_rows:7,source_max_survey:time('2026-08-01'),matched:10,canonical_rows:13,regimens_without_complete_interval:2},true);
  expect(text).toContain('7 documented medication source rows');expect(text).toContain('Reviewed surveys extend through 2026-08-01');
  expect(text).toContain('Matched 10 of 13 reviewed surveys; 3 unmatched');expect(text).toContain('2 regimens lack a complete interval');
  expect(comparisonCoverage({source_rows:0,matched:0,canonical_rows:0,regimens_without_complete_interval:0},true)).toContain('0 regimens lack a complete interval');
});

test('top programs use metric-specific eligible IDs, at least five finite scores and ascending medians independently per mode',()=>{
  const conditions=[condition('a',7),condition('b',2),condition('c',3),condition('d',1),condition('short',0,4),condition('invalid',0)];
  conditions[5].points[0].value=NaN;conditions[5].points[1].time=NaN;
  const metric={conditions,top:{open_loop:conditions.map(c=>c.id),closed_loop:['a','c']}};
  expect(topPrograms(metric,'open_loop').map(c=>c.id)).toEqual(['d','b','c']);
  expect(topPrograms(metric,'closed_loop').map(c=>c.id)).toEqual(['c','a']);
  expect(topPrograms({conditions},'open_loop')).toEqual([]);expect(topPrograms({...metric,top:{}},'open_loop')).toEqual([]);
});

test('compact labels remain bounded and escaped, while setting tooltips retain full units and qualify open-loop thresholds',()=>{
  expect(compactLabel('')).toBe('');expect(compactLabel('<a> & b')).toBe('&lt;a&gt; &amp; b');
  expect(compactLabel('This very long descriptive regimen name continues well beyond the plotting margin')).toContain('…');
  const summary=conditionSummary({...condition('a',2),label:'<Group> "A"',settings:[{label:'L contacts',value:'C+2−'},{label:'L frequency',value:'55 Hz'},{label:'L lower threshold',value:'20 LSB'}]});
  expect(summary).toContain('&lt;Group&gt; &quot;A&quot;');expect(summary).toContain('L contacts: C+2−');expect(summary).toContain('L frequency: 55 Hz');
  expect(summary).toContain('Stored L lower threshold (not controlling stimulation): 20 LSB');
  expect(conditionSummary({label:'Medication',drug_class:'Opioid',status:'PRN available',dose:'5 mg',background:'Concurrent regimen'})).toContain('status: PRN available');
  expect(conditionSummary({label:'CL',mode:'closed_loop',settings:[{label:'Lower threshold',value:'20 LSB'}]})).not.toContain('not controlling');
});

test('boxes use exact eligible values and deterministic survey dots with readable axes and settings hover',()=>{
  const metric={label:'NRS',range:[0,10]},conditions=[{...condition('a',3),points:points([1,2,3,4,5])}];
  const vertical=conditionPlot(metric,conditions);
  expect(vertical.traces).toHaveLength(2);expect(vertical.traces[0]).toMatchObject({type:'box',y:[1,2,3,4,5],boxpoints:false,orientation:'v'});
  expect(vertical.traces[1].y).toEqual([1,2,3,4,5]);expect(vertical.traces[1].customdata[0]).toEqual(['2026-08-01 12:00:00',1]);
  expect(vertical.layout.xaxis.ticktext[0]).toContain('n=5 · median 3');expect(vertical.layout.yaxis.range).toEqual([0,10]);
  expect(conditionPlot(metric,conditions).traces[1].x).toEqual(vertical.traces[1].x);
  const horizontal=conditionPlot(metric,conditions,true);
  expect(horizontal.traces[0]).toMatchObject({orientation:'h',x:[1,2,3,4,5]});expect(horizontal.layout.yaxis.autorange).toBe('reversed');
  expect(horizontal.layout.height).toBeGreaterThanOrEqual(350);expect(conditionPlot(metric,[]).traces).toEqual([]);
});

const episode=(id,extra={})=>({id,name:`Drug ${id}`,drug_class:'Class A',start:time('2026-08-01'),end:time('2026-08-20'),dose:'5 mg',frequency:'Daily',route:'Oral',timing:'Morning',prn:false,...extra});
test('medication intervals preserve class ordering, overlap, PRN and supportive distinctions, and stage boundaries',()=>{
  const episodes=[episode('z',{drug_class:'Class Z',drug_class_order:0,prn:true,supportive:true}),episode('a',{drug_class_order:1}),episode('b',{drug_class:'Class B'})];
  const phases=[{label:'Stage 1',start:time('2026-07-01'),color:'#123456'},{label:'Future',start:time('2027-01-01'),color:'#777777'}];
  const plot=medicationTimeline(episodes,'2026-09-03',time('2026-07-01'),phases);
  expect(plot.traces).toHaveLength(3);expect(plot.traces[0].hovertemplate).toContain('Drug z');
  expect(plot.traces[0]).toMatchObject({mode:'lines+markers',line:{width:5,dash:'dot'},opacity:0.6});
  expect(plot.traces[0].hovertemplate).toContain('PRN available; use is not confirmed');
  expect(plot.traces[1].line.width).toBe(10);expect(plot.traces[1].hovertemplate).toContain('5 mg');
  expect(plot.traces[0].x).toEqual(plot.traces[1].x);expect(plot.layout.shapes.filter(shape=>shape.type==='line')).toHaveLength(1);expect(plot.layout.annotations.some(item=>item.text==='Stage 1')).toBe(true);
});

test('unknown dates are endpoint markers only, ongoing is explicit and clipped intervals retain their real dates in hover',()=>{
  const start=time('2026-08-01');
  const episodes=[episode('before',{start:time('2026-07-01'),pre_trial:true,ongoing:true,end:null}),episode('unknown-start',{start:null}),episode('unknown-end',{end:null,ongoing:false}),episode('unknown-both',{start:null,end:null}),episode('already-ended',{end:time('2026-07-31')}),episode('future',{start:time('2027-01-01')}),episode('later-end',{end:time('2027-01-01')})];
  const plot=medicationTimeline(episodes,'2026-09-03',start);
  expect(plot.traces).toHaveLength(4);
  const before=plot.traces.find(t=>t.hovertemplate.includes('Drug before'));
  expect(before.x).toEqual(['2026-08-01 12:00:00','2026-09-03 23:59:59']);expect(before.marker.symbol).toEqual(['triangle-left','triangle-right']);expect(before.hovertemplate).toContain('2026-07-01');
  const unknownStart=plot.traces.find(t=>t.hovertemplate.includes('Drug unknown-start'));
  expect(unknownStart.mode).toBe('markers');expect(unknownStart.x).toHaveLength(1);expect(unknownStart.hovertemplate).toContain('Start date not recorded');
  const unknownEnd=plot.traces.find(t=>t.hovertemplate.includes('Drug unknown-end'));expect(unknownEnd.mode).toBe('markers');expect(unknownEnd.hovertemplate).toContain('End date not recorded');
  expect(plot.traces.find(t=>t.hovertemplate.includes('Drug later-end')).x[1]).toBe('2026-09-03 23:59:59');
  expect(medicationTimeline([], '2026-09-03').traces).toEqual([]);
  expect(medicationTimeline([episode('normal')],'2026-09-03').layout.xaxis.range).toBeUndefined();
});


test('one stimulation axis separates OL and CL and draws OFF reference quantiles from nonmissing scores',()=>{
  const metric={label:'NRS',range:[0,10],baseline:{points:points([1,2,3,4,5])}};
  const plot=stimulationPlot(metric,[condition('ol',2)],[{...condition('cl',3),mode:'closed_loop'}]);
  expect(plot.layout.xaxis.tickvals).toEqual([0,4]);expect(plot.traces[2].x).toEqual([4,4,4,4,4]);
  expect(plot.offReference).toEqual({count:5,p30:2.2,median:3,p70:3.8,countLabel:'n = 5 surveys (5 days)'});
  expect(plot.layout.shapes.filter(shape=>shape.xref==='paper').map(shape=>shape.y0)).toEqual([2.2,3,3.8]);
  expect(plot.layout.shapes.filter(shape=>shape.xref==='paper').map(shape=>shape.line.color)).toEqual(['#C62828','#2E7D32','#C62828']);
  expect(stimulationPlot({...metric,baseline:null},[],[]).offReference).toBeUndefined();
  expect(stimulationPlot({...metric,baseline:{points:[{value:NaN}]}},[],[]).offReference).toBeUndefined();
});

test('medication condition bands display clinical class headings, preserve every condition and keep rows compact',()=>{
  const conditions=[{...condition('z',1),drug_class:'Alphabetically last',drug_class_order:0},{...condition('a',2),drug_class:'Alphabetically first',drug_class_order:1},{...condition('b',3),drug_class:'Alphabetically first',drug_class_order:1}];
  expect(orderedMedicationConditions(conditions).map(c=>c.id)).toEqual(['z','a','b']);
  const plot=medicationConditionPlot({label:'NRS',range:[0,10]},conditions);
  expect(plot.layout.annotations.map(a=>a.text)).toEqual(['<b>Alphabetically last</b>','<b>Alphabetically first</b>']);
  expect(plot.layout.shapes.filter(shape=>shape.type==='rect')).toHaveLength(2);expect(plot.layout.yaxis.tickvals).toEqual([0,1.7,2.7]);
  expect(plot.traces.filter(t=>t.type==='box')).toHaveLength(3);expect(plot.layout.height).toBe(350);
  expect(medicationConditionPlot({label:'NRS',range:[0,10]},[]).layout.yaxis.range).toEqual([0.6,-1]);
});

test('ongoing medication with unknown start is a boundary marker, not a fabricated active interval',()=>{
  const drug=episode('unknown',{start:null,end:null,ongoing:true});
  const plot=medicationTimeline([drug],'2026-09-03',time('2026-07-01'));
  expect(plot.traces).toHaveLength(1);expect(plot.traces[0]).toMatchObject({mode:'markers',x:['2026-07-01 12:00:00'],marker:{symbol:['diamond-open']}});
  expect(plot.traces[0].hovertemplate).toContain('Start date not recorded');
  expect(medicationTimeline([drug],'2026-09-03').traces[0].x).toEqual(['2026-09-03 23:59:59']);
});


test('long clinical class names appear as headers instead of hiding drug names in medication row labels',()=>{
  const drug=episode('actual',{name:'Visible drug',drug_class:'A very long clinical class category that exceeds forty eight characters',dose:'5 mg',frequency:'Daily'});
  const plot=medicationTimeline([drug],'2026-09-03');
  expect(plot.layout.yaxis.ticktext[0]).toContain('Visible drug');expect(plot.layout.yaxis.ticktext[0]).toContain('5 mg');
  expect(plot.layout.yaxis.ticktext[0]).not.toContain('clinical class');expect(plot.layout.annotations[0].text.replace(/<br>/g,' ')).toContain(drug.drug_class);expect(plot.layout.shapes[0].type).toBe('rect');
});

test('opaque median strokes stay above points at exact scores across OL/CL and medication class gaps',()=>{
  const metric={label:'NRS',range:[0,10]},a=condition('a',0),b={...condition('b',6),mode:'closed_loop'};
  const vertical=stimulationPlot(metric,[a],[b]);
  const lines=vertical.layout.shapes.filter(s=>s.name==='Condition median');
  expect(lines).toHaveLength(2);
  expect(lines[0]).toMatchObject({x0:-0.275,x1:0.275,y0:0,y1:0,layer:'above',line:{color:'#172B4D',width:3}});
  expect(lines[1].x0).toBeCloseTo(3.725);expect(lines[1].x1).toBeCloseTo(4.275);
  expect(lines[1].y0).toBe(6);expect(lines[1].y1).toBe(6);
  expect(vertical.traces[0].opacity).toBe(1);expect(vertical.traces[0].fillcolor).toBe('rgba(53,102,155,0.15)');
  const horizontal=medicationConditionPlot(metric,[{...a,drug_class:'A'},{...b,drug_class:'B'}]);
  const hLines=horizontal.layout.shapes.filter(s=>s.name==='Condition median');
  expect(hLines[0]).toMatchObject({x0:0,x1:0,y0:-0.275,y1:0.275,layer:'above'});
  expect(hLines[1]).toMatchObject({x0:6,x1:6});
  expect(hLines[1].y0).toBeCloseTo(1.425);expect(hLines[1].y1).toBeCloseTo(1.975);
  expect(conditionPlot(metric,[]).layout.shapes).toEqual([]);
});

const sourceSettings=(extra=[])=>[
  {label:'Cycle',value:'On'},{label:'cycle on sec',value:'360'},{label:'cycle off sec',value:'720'},
  ...['Left','Right'].flatMap(side=>[
    {label:`${side} contacts`,value:side==='Left'?'c+2-':'c+9-10-'},
    {label:`${side} rate hz`,value:'55'}, {label:`${side} amplitude mA`,value:side==='Left'?'3.5':'3'},
    {label:`${side} pulse width us`,value:side==='Left'?'100':'150'}]),...extra];

test('stimulation settings labels retain timing, contact, frequency, amplitude and pulse-width units without OL sensing',()=>{
  const text=stimulationAxisSettings({mode:'open_loop',settings:sourceSettings([
    {label:'Left target',value:'L GPi'},{label:'Right target',value:'R Thal'},
    {label:'Left sensing frequency hz',value:'23.44'},{label:'Left lower lfp threshold (LSB)',value:'10'}])});
  expect(text).toBe('6 min ON / 12 min OFF<br>L GPi C+2-<br>55 Hz · 3.5 mA · 100 µs<br>R Thal C+9-10-<br>55 Hz · 3 mA · 150 µs');
  expect(text).not.toMatch(/sensing|threshold|23.44/i);
  expect(stimulationAxisSettings({settings:[{label:'Cycle',value:'Off'}]})).toBe('Continuous stimulation');
  expect(stimulationAxisSettings({settings:[{label:'Cycle',value:'On'},{label:'cycle on sec',value:'30'},{label:'cycle off sec',value:'NA'}]})).toBe('30 s ON / ? OFF');
  expect(stimulationAxisSettings({settings:[{label:'Left contacts',value:'<c+2->'},{label:'Left rate hz',value:'NaN'},{label:'Left pulse width us',value:'NA'},{label:'Right contacts',value:'NA'}]})).toBe('L &lt;C+2-&gt;<br>? Hz · ? mA · ? µs');
  expect(stimulationAxisSettings({})).toBe('Settings not available');
});

test('closed-loop axis uses program limits rather than capture amplitudes and does not substitute static current for missing limits',()=>{
  const adaptive=[{label:'Left adaptive status',value:'running'},
    {label:'Left lower limit mA',value:'0'},{label:'Left upper limit mA',value:'1.6'},
    {label:'Left lower capture amplitude mA',value:'0.2'},{label:'Left upper capture amplitude mA',value:'1.2'}];
  const closed={mode:'closed_loop',settings:sourceSettings(adaptive)};
  expect(stimulationAxisSettings(closed)).toContain('55 Hz · 0–1.6 mA');
  expect(stimulationAxisSettings(closed)).not.toContain('0.2–1.2 mA');
  expect(conditionSummary({...closed,label:'CL'})).toContain('Left upper capture amplitude mA: 1.2');
  expect(stimulationAxisSettings({mode:'open_loop',settings:sourceSettings(adaptive)})).toContain('55 Hz · 3.5 mA');
  for(const extra of [[{label:'Left lower limit mA',value:'NA'}],[{label:'Left upper limit mA',value:'NA'}],[{label:'Left lower limit mA',value:'4'}]]) {
    const text=stimulationAxisSettings({mode:'closed_loop',settings:sourceSettings([...adaptive,...extra])});
    expect(text).toContain('55 Hz · ? mA');expect(text).not.toContain('3.5 mA');
  }
});

test('finalized OL stays fourth even when already ranked and retains sparse scores instead of applying the top-three cutoff',()=>{
  const a={...condition('a',2),settings:sourceSettings()},b={...condition('b',4),mode:'closed_loop'},sparse=condition('sparse',7,2);
  const metric={label:'NRS',range:[0,10],conditions:[a,b,sparse]};
  const reference={available:true,id:'a',mode:'open_loop',settings:sourceSettings()};
  const plot=stimulationPlot(metric,[a],[b],reference);
  expect(plot.layout.xaxis.tickvals).toEqual([0,3,5]);
  expect(plot.traces.filter(t=>t.type==='box').map(t=>t.name)).toEqual(['Program a','Finalized OL','Program b']);
  expect(plot.traces[0].y).toEqual(plot.traces[2].y);
  expect(plot.programs[1]).toMatchObject({title:'Finalized OL',countLabel:'n = 5 surveys (5 days)'});
  expect(plot.programs[1].settings).toContain('6 min ON / 12 min OFF');
  const medians=plot.layout.shapes.filter(s=>s.name==='Condition median');
  expect(medians.map(s=>(s.x0+s.x1)/2)).toEqual([0,3,5]);
  expect(medians[1]).toMatchObject({y0:2,y1:2,line:{width:3,color:'#172B4D'}});
  const small=stimulationPlot(metric,[],[],{...reference,id:'sparse'});
  expect(small.traces[0].y).toEqual([7,7]);expect(small.programs[0].countLabel).toBe('n = 2 surveys (2 days)');
  expect(small.minWidth).toBeUndefined();expect(small.fitWidth).toBe(true);expect(small.layout.height-small.layout.margin.b-small.layout.margin.t).toBeGreaterThanOrEqual(300);
});

test('finalized reference with no matching eligible program reserves a labeled slot without invented scores, box or median',()=>{
  const metric={label:'NRS',range:[0,10],conditions:[]};
  const reference={available:true,id:'reference',mode:'open_loop',settings:sourceSettings()};
  const plot=stimulationPlot(metric,[],[],reference);
  expect(plot.traces).toEqual([]);expect(plot.layout.xaxis.tickvals).toEqual([3]);
  expect(plot.programs[0].countLabel).toBe('n = 0 surveys (0 days)');
  expect(plot.layout.shapes.filter(s=>s.name==='Condition median')).toEqual([]);
  expect(finalizedProgram({...metric,conditions:[{...condition('reference',2),mode:'closed_loop'}]},reference).count).toBe(0);
  expect(finalizedProgram(metric,null)).toBeNull();expect(finalizedProgram(metric,{...reference,available:false})).toBeNull();
  expect(finalizedProgram(metric,{...reference,id:''})).toBeNull();expect(finalizedProgram(metric,{...reference,mode:'closed_loop'})).toBeNull();
});

test('current CL is fixed fourth on the closed-loop side, including sparse, duplicated and zero-survey reference cases',()=>{
  const ol=condition('ol',2),cl={...condition('cl',4,2),mode:'closed_loop'};
  const metric={label:'NRS',range:[0,10],conditions:[ol,cl]};
  const reference={available:true,id:'ol',mode:'open_loop',settings:[]},current={available:true,id:'cl',mode:'closed_loop',settings:[]};
  const plot=stimulationPlot(metric,[ol],[cl],reference,current);
  expect(plot.layout.xaxis.tickvals).toEqual([0,3,5,8]);
  expect(plot.traces.filter(t=>t.type==='box').map(t=>t.name)).toEqual(['Program ol','Finalized OL','Program cl','Current CL']);
  expect(plot.programs[3]).toMatchObject({title:'Current CL',countLabel:'n = 2 surveys (2 days)'});
  expect(plot.layout.shapes.filter(s=>s.name==='Condition median').map(s=>(s.x0+s.x1)/2)).toEqual([0,3,5,8]);
  const empty=stimulationPlot({...metric,conditions:[]},[],[],null,current);
  expect(empty.layout.xaxis.tickvals).toEqual([8]);expect(empty.layout.xaxis.range).toEqual([-0.65,8.65]);
  expect(empty.programs[0].countLabel).toBe('n = 0 surveys (0 days)');expect(empty.traces).toEqual([]);
});

test('current home-program labels use native reviewed targets, contacts and unit-bearing settings without flattening guesses',()=>{
  const home={group:[{label:'Cycling',value:'Off'}],left:[
    {label:'Tablet target',value:'GPi'},{label:'Stimulation contacts',value:'Case+, 2−'},
    {label:'Frequency',value:'55 Hz'},{label:'Adaptive amplitude range',value:'0 mA to 3.5 mA'},
    {label:'Pulse width',value:'100 µs'},{label:'Adaptive state',value:'Running'},
    {label:'Biomarker center frequency',value:'23.44 Hz'}],right:[
    {label:'Tablet target',value:'VIM'},{label:'Stimulation contacts',value:'Case+, 9a−, 9b−, 9c−, 10a−, 10b−, 10c−'},
    {label:'Frequency',value:'55 Hz'},{label:'Fixed / paused amplitude',value:'3 mA'},{label:'Pulse width',value:'150 µs'}]};
  const result=stimulationAxisSettings({home_settings:home,settings:sourceSettings()});
  expect(result).toBe('Continuous stimulation<br>L GPi C+2−<br>55 Hz · 0 mA to 3.5 mA · 100 µs<br>R VIM C+9a−9b−9c−10a−10b−10c−<br>55 Hz · 3 mA · 150 µs');
  expect(result).not.toContain('23.44');expect(result).not.toContain('6 min');
  const reference={available:true,id:'dynamic',mode:'closed_loop',home_settings:home,settings:[]};
  const plot=stimulationPlot({label:'NRS',range:[0,10],conditions:[]},[],[],null,reference);
  expect(plot.programs[0].settings).toContain('55 Hz · 0 mA to 3.5 mA · 100 µs');expect(plot.traces).toEqual([]);
});

test('native home axis settings preserve unknowns, escape source text and never invent units or numeric settings',()=>{
  expect(stimulationAxisSettings({home_settings:{}})).toBe('Settings not available');
  const home={group:[{label:'Cycling',value:'On · on 30 s / off 60 s'}],left:[{label:'Tablet target',value:'<test>'},{label:'Amplitude',value:'2 mA'}],right:[{label:'Adaptive state',value:'Running'}]};
  const text=stimulationAxisSettings({home_settings:home});
  expect(text).toContain('Cycling On · on 30 s / off 60 s');expect(text).toContain('L &lt;test&gt; Contacts not recorded');
  expect(text).toContain('Frequency not recorded · 2 mA');expect(text).toContain('R Contacts not recorded');
  expect(text).toContain('Amplitude not recorded');expect(text).toContain('Pulse width not recorded');
});

test('survey-day counts use eligible points and Pacific dates across UTC midnight and daylight-saving transitions',()=>{
  const timed=[
    {time:Date.parse('2026-08-02T00:30:00Z')/1000,value:2},
    {time:Date.parse('2026-08-02T06:59:00Z')/1000,value:3},
    {time:Date.parse('2026-08-02T07:00:00Z')/1000,value:4},
    {time:NaN,value:8},{time:time('2026-08-03'),value:NaN}];
  expect(surveyCount({count:99,points:timed})).toBe('n = 3 surveys (2 days)');
  expect(surveyCount({points:[]})).toBe('n = 0 surveys (0 days)');
  expect(surveyCount({points:['2026-11-01T08:30:00Z','2026-11-01T09:30:00Z'].map(date=>({time:Date.parse(date)/1000,value:1}))})).toBe('n = 2 surveys (1 days)');
});

test('split mode comparisons preserve every score/reference slot while only survey points trigger detailed hover',()=>{
  const ol=condition('ol',2),cl={...condition('cl',4),mode:'closed_loop',settings:sourceSettings([{label:'Cycle',value:'Off'},{label:'Left adaptive mode',value:'SINGLE_THRESHOLD_DIRECT'}])};
  const metric={label:'NRS',range:[0,10],conditions:[ol,cl]};
  const current={available:true,id:'cl',mode:'closed_loop',settings:cl.settings};
  const plot=stimulationPlot(metric,[ol],[cl],null,current,{mode:'closed_loop',participant:'RCS08'});
  expect(plot.fitWidth).toBe(true);expect(plot.minWidth).toBeUndefined();expect(plot.layout.hovermode).toBe('closest');
  expect(plot.layout.xaxis.tickvals).toEqual([0,3]);expect(plot.layout.xaxis.range).toEqual([-0.65,3.65]);
  expect(plot.programs.map(program=>program.title)).toEqual(['CL 1','Current CL']);
  expect(plot.traces.filter(trace=>trace.type==='box').map(trace=>trace.y)).toEqual([cl.points.map(p=>p.value),cl.points.map(p=>p.value)]);
  for(const box of plot.traces.filter(trace=>trace.type==='box')) {expect(box.hoverinfo).toBe('skip');expect(box.hovertemplate).toBeUndefined();}
  expect(plot.traces[1].hovertemplate).toContain('Mode: Single threshold direct');
  expect(plot.traces[1].hovertemplate).toContain('L GPe C+2-');expect(plot.traces[1].hovertemplate).toContain('R MD Thal C+9-10-');
  expect(plot.traces[1].hovertemplate).not.toContain('Continuous');
  expect(plot.traces[1].hovertemplate).toContain('n = 5 surveys (5 days)');
  expect(plot.layout.shapes.filter(shape=>shape.name==='Condition median').map(shape=>(shape.x0+shape.x1)/2)).toEqual([0,3]);
});

test('native CL settings use explicit mode and sensing source with units, including zero thresholds and unknown fields',()=>{
  const original={label:'<CL>',mode:'closed_loop',points:[],home_settings:{group:[{label:'Cycling',value:'Off'}],left:[
    {label:'Tablet target',value:'GPi'},{label:'Stimulation contacts',value:'Case+, 2−'},
    {label:'Frequency',value:'55 Hz'},{label:'Amplitude',value:'1 mA'},{label:'Pulse width',value:'100 µs'},
    {label:'Threshold mode',value:'Dual threshold direct'},{label:'Sensing source hemisphere',value:'Right'},
    {label:'Sensing contacts',value:'8–10'},{label:'Biomarker center frequency',value:'23.44 Hz'},
    {label:'Lower LFP threshold',value:'0 LFP Power (LSB)'},{label:'Upper LFP threshold',value:'167 LFP Power (LSB)'},
    {label:'Adaptive state',value:'Paused'}],right:[{label:'Stimulation contacts',value:'Case+, 9−'}]}};
  const before=JSON.stringify(original),text=stimulationSummary(original,'RCS08');
  expect(text).toContain('&lt;CL&gt;');expect(text).toContain('L GPe C+2−<br>55 Hz · 1 mA · 100 µs');
  expect(text).toContain('Mode: Dual threshold direct');expect(text).toContain('BrainSense R MD Thal: 8–10 · 23.44 Hz');
  expect(text).toContain('lower 0 LFP Power (LSB) · upper 167 LFP Power (LSB)');
  expect(text).toContain('Mode: not recorded');expect(text).toContain('frequency not recorded');expect(text).toContain('Adaptive state: Paused');
  expect(text).not.toContain('Continuous');expect(JSON.stringify(original)).toBe(before);
});

test('legacy sensing values retain source scope, unknowns and explicit ganged metadata without borrowing settings',()=>{
  const extra=[{label:'Cycle',value:'Off'},{label:'Left adaptive mode',value:'AdaptiveModeDef.DUAL_THRESHOLD_DIRECT'},
    {label:'Left sensing channel',value:'0–2'},{label:'Left sensing frequency hz',value:'23.44'},
    {label:'Left lower lfp threshold (LSB)',value:'0'},{label:'Left upper lfp threshold (LSB)',value:'167'},
    {label:'Left ganged to',value:'Right'},{label:'Right ganged to',value:'NOT_GANGED'}];
  const original={label:'CL',mode:'closed_loop',settings:sourceSettings(extra),points:[]},before=JSON.stringify(original);
  const lines=stimulationSettingLines(original,'RCS08');
  expect(lines).toContain('Mode: Dual threshold direct');expect(lines).toContain('BrainSense L GPe: 0–2 · 23.44 Hz');
  expect(lines).toContain('LFP thresholds: lower 0 · upper 167 LSB');
  expect(lines).toContain('Ganged to: R MD Thal (sensing values above are recorded for L GPe)');
  expect(lines.filter(line=>line.startsWith('Ganged to'))).toHaveLength(1);
  expect(lines).toContain('BrainSense R MD Thal: contacts not recorded · frequency not recorded');
  const encoded={...original,settings:sourceSettings([...extra,
    {label:'Left sensing channel',value:'LfpMontageDef.ZERO_AND_TWO'},
    {label:'Right sensing channel',value:'LfpMontageDef.ONE_AND_THREE'}])};
  expect(stimulationSettingLines(encoded,'RCS08')).toContain('BrainSense L GPe: 0–2 · 23.44 Hz');
  expect(stimulationSettingLines(encoded,'RCS08')).toContain('BrainSense R MD Thal: 9–11 · frequency not recorded');
  expect(JSON.stringify(original)).toBe(before);
  expect(stimulationDetailRows({mode:'open_loop',settings:[{label:'Left target',value:'L GPi'},{label:'Lower threshold',value:0}]},'RCS08')).toEqual(['Left target: L GPe','Stored Lower threshold (not controlling stimulation): 0']);
  expect(stimulationDetailRows({})).toEqual([]);
});

test('medication plots expose complete source row labels for responsive keys without minimum widths',()=>{
  const name='A complete unusually long medicine name extending beyond the old forty-eight-character limit';
  const med={id:'long',name,drug_class:'Analgesic',drug_class_order:1,dose:'10 mg',frequency:'daily',start:time('2026-07-01'),ongoing:true};
  const timeline=medicationTimeline([med],'2026-09-03');
  expect(timeline.fitWidth).toBe(true);expect(timeline.minWidth).toBeUndefined();expect(timeline.rowLabels).toEqual([`1. Analgesic · ${name} · 10 mg · daily`]);
  const conditions=medicationConditionPlot({label:'NRS',range:[0,10]},[{...med,label:name,count:1,median:4,points:[{time:time('2026-07-01'),value:4}]}]);
  expect(conditions.fitWidth).toBe(true);expect(conditions.minWidth).toBeUndefined();expect(conditions.rowLabels[0]).toContain(name);expect(conditions.rowLabels[0]).toContain('n=1 · median 4');
});
