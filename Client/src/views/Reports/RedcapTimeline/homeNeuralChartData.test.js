import {homeNeuralPlot,homeNeuralLayout,neuralTime,neuralSourceLabel,neuralSegmentDescription,neuralSettingsLines,neuralHoverLines,neuralContactLabel} from './homeNeuralChartData';

const time=Date.parse('2026-09-01T19:00:00Z')/1000;
const period={id:'current',label:'Current settings',start:time,end:time+7200};
const segment={id:'visit-a:left',start:time,end:time+7200,mode:'Closed loop · dual threshold',adaptive_state:'Running',
  sensing_side:'right',mapping_status:'Contralateral source confirmed',sensing_contacts:'8–10',power_band_label:'18–22 Hz',center_frequency_hz:20,
  settings:{group:[{label:'Group',value:'Group A'}],left:[{label:'Stimulation contacts',value:'C+2-'},{label:'Frequency',value:'130 Hz'}],right:[]},
  thresholds:[{label:'Lower threshold',value:0},{label:'Upper threshold',value:25}],evidence:'Reviewed home configuration',
  points:[{time,power:0,amplitude:0},{time:time+600,power:12,amplitude:2.4}]};
const panel={side:'left',segments:[segment]};
const plot=(overrides={})=>homeNeuralPlot({...panel,...overrides},period,'RCS08');

test('keeps controller source contralateral, stimulation side distinct, zero observable and units explicit',()=>{
 const result=plot();
 expect(result.traces).toHaveLength(4);expect(result.observedPower).toBe(2);expect(result.observedAmplitude).toBe(2);
 expect(result.latestTime).toBe(time+600);
 expect(result.traces[0]).toMatchObject({name:'R MD Thal biomarker',y:[0,12],yaxis:'y',mode:'lines+markers',connectgaps:false});
 expect(result.traces[1]).toMatchObject({name:'L GPe stimulation amplitude',y:[0,2.4],yaxis:'y2'});
 expect(result.traces[0].customdata[0][1]).toContain('Biomarker: 0 LSB');
 expect(result.traces[0].customdata[0][1]).toContain('Stimulation amplitude: 0 mA');
 expect(result.traces[0].customdata[0][1]).toContain('Biomarker source: R MD Thal<br>Sensing contacts: 8 and 10');
 expect(result.traces[0].customdata[0][1]).toContain('18–22 Hz');
 expect(result.traces[0].customdata[0][1]).toContain('L GPe C+2-');
 expect(result.traces[0].hovertemplate).toBe('%{customdata[1]}<extra></extra>');
 expect(result.traces[2]).toMatchObject({y:[0,0],line:{dash:'dash'},yaxis:'y'});
 expect(result.traces[3]).toMatchObject({y:[25,25],line:{dash:'dot'}});
});

test('known values connect at 20 minutes, longer gaps break, and conflicts/missing values break each series independently',()=>{
 const result=plot({segments:[{...segment,points:[
  {time,power:1,amplitude:2},{time:time+1200,power:2,amplitude:3},
  {time:time+2401,power:3,amplitude:4},{time:time+3001,power:8,power_conflict:true,amplitude:5},
  {time:time+3601,power:4,amplitude:10,amplitude_conflict:true},{time:time+4201,power:null,amplitude:null},
  {time:time+4801,power:NaN,amplitude:'0'},{time:time+5401,power:0,amplitude:0},
 ]}]});
 expect(result.traces[0].y).toEqual([1,2,null,3,null,4,null,null,0]);
 expect(result.traces[1].y).toEqual([2,3,null,4,5,null,null,null,0]);
 expect(result.traces[0].customdata[4][1]).toContain('Biomarker: Not established');
 expect(result.traces[1].customdata[5][1]).toContain('Stimulation amplitude: Not established');
 expect(result.traces[0].customdata[2]).toBeNull();
});

test('sorts observations and applies half-open visit/segment boundaries so shared visit samples cannot appear in both windows',()=>{
 const result=plot({segments:[{...segment,start:time-600,end:time+3600,points:[
  {time:time+1200,power:3},{time:time-1,power:8},{time,power:1},{time:time+3600,power:9},
  {time:'not a date',power:99},{time:time+600,power:2},
 ]}]});
 expect(result.traces[0].y).toEqual([1,2,3]);expect(result.observedAmplitude).toBe(0);
 expect(result.traces[1].x).toEqual(['2026-09-01 12:00:00','2026-09-01 13:00:00']);
 const prior=homeNeuralPlot(panel,{...period,start:time-7200,end:time},'RCS08');
 expect(prior.traces).toEqual([]);
});

test('configuration changes remain separate even with adjacent samples and threshold periods cannot leak across settings',()=>{
 const result=plot({segments:[{...segment,end:time+600,thresholds:[{value:4}]},
  {...segment,id:'b',start:time+600,thresholds:[{label:'Single',value:6}],sensing_side:'left',mode:'Single threshold'}]});
 expect(result.traces.filter(t=>t.mode==='lines+markers')).toHaveLength(4);
 expect(result.traces[2].x[1]).toBe(result.traces[5].x[0]);
 expect(result.traces[2].hovertemplate).toContain('Configured threshold');
 expect(result.traces[3].name).toBe('L GPe biomarker');
 expect(result.traces[3].customdata[0][0]).toBe('b');
});

test.each(['Sensing only','sensing_only','sensing-only'])("sensing-only mode %s never gets thresholds even when a malformed payload includes them",mode=>{
 expect(plot({segments:[{...segment,mode}]}).traces).toHaveLength(2);
});

test('unprovided, null and nonfinite thresholds remain absent, a valid zero guide remains',()=>{
 expect(plot({segments:[{...segment,thresholds:undefined}]}).traces).toHaveLength(2);
 expect(plot({segments:[{...segment,thresholds:[{value:null},{value:'4'},{value:Infinity},{value:0}]}]}).traces).toHaveLength(3);
});

test('unresolved sensing is explicit; an unknown side is never labeled ipsilateral',()=>{
 const result=plot({side:'right',segments:[{...segment,sensing_side:null,mapping_status:null,mode:null,adaptive_state:null,evidence:null,sensing_contacts:null,power_band_label:null,center_frequency_hz:null,settings:null}]});
 expect(result.traces[0].name).toBe('Sensing source unresolved biomarker');
 expect(result.traces[1].name).toBe('R MD Thal stimulation amplitude');
 expect(result.descriptions[0]).toMatchObject({source:'Sensing source unresolved',contacts:'Contacts not recorded',band:'Power band not recorded',mode:'Mode not established'});
 expect(result.traces[0].customdata[0][1]).toContain('Adaptive state: Not recorded');
 expect(result.traces[0].customdata[0][1]).toContain('Control mapping: Not established');
 expect(neuralSourceLabel('left','other')).toBe('Left lead');expect(neuralSourceLabel('right','other')).toBe('Right lead');
});

test('center frequency does not fabricate a band width and source strings are escaped in HTML hover fields',()=>{
 expect(neuralSegmentDescription({...segment,power_band_label:null},'RCS08').band).toBe('20 Hz center · band width not recorded');
 const result=plot({segments:[{...segment,sensing_contacts:'<img>',evidence:'<script>alert(1)</script>',thresholds:[{label:'<b>x</b>',value:5}]}]});
 expect(result.traces[0].customdata[0][1]).not.toContain('<img>');
 expect(result.traces[0].customdata[0][1]).not.toContain('script');
 expect(result.traces[2].hovertemplate).toContain('&lt;b&gt;x&lt;/b&gt;');
});

test('compact hover contains only plotted-side stimulation, shared cycling and sensing context; complete other-side settings stay in details',()=>{
 const extended={...segment,settings:{...segment.settings,group:[{label:'Group',value:'Group A'},{label:'Cycling',value:'Off'},{label:'High-pass filter',value:'100 Hz'}],
  left:[{label:'Stimulation contacts',value:'C+2-'},{label:'Frequency',value:'130 Hz'},{label:'Amplitude',value:'3 mA'},{label:'Pulse width',value:'60 µs'}],
  right:[{label:'Stimulation contacts',value:'C+11-'},{label:'Frequency',value:'90 Hz'}]}};
 extended.threshold_status='Active configured threshold guide';
 const detail=plot({segments:[extended]}).traces[0].customdata[0][1];
 expect(detail).toContain('L GPe C+2-<br>130 Hz · 3 mA · 60 µs');expect(detail).toContain('Cycling: Off');
 expect(detail).toContain('Lower threshold: 0 LSB');expect(detail).not.toContain('C+11-');expect(detail).not.toContain('90 Hz');expect(detail).not.toContain('High-pass');
 expect(detail).toContain('Active configured threshold guide');
 const programs={settings:{left:[{label:'Program 1 · Stimulation contacts',value:'C+1-'},{label:'Program 1 · Adaptive amplitude range',value:'0 mA to 3 mA'},
  {label:'Program 2 · Fixed / paused amplitude',value:'2 mA'}]}};
 expect(neuralSettingsLines(programs,'left','RCS08')).toEqual(['L GPe · Program 1 C+1-','range 0 mA to 3 mA','L GPe · Program 2 Contacts not recorded','paused 2 mA']);
 expect(neuralSettingsLines({settings:{left:[{label:'Stimulation contacts',value:'C+1-'}]}},'left','RCS08')).toEqual(['L GPe C+1-']);
 expect(neuralHoverLines([''])).toBe('');expect(neuralHoverLines(['<long>'.repeat(30)]).split('<br>').every(line=>line.length<110)).toBe(true);
});

test('empty and invalid scope has no fabricated observations and no invalid dates',()=>{
 expect(plot({segments:undefined}).traces).toEqual([]);
 expect(plot({segments:undefined}).latestTime).toBeNull();
 expect(plot({segments:[{...segment,points:undefined,thresholds:[]}]})).toMatchObject({traces:[],observedPower:0,observedAmplitude:0});
 for(const invalid of [{start:null},{end:null},{start:time+9000},{end:time-100}])
  expect(plot({segments:[{...segment,...invalid}]}).traces).toEqual([]);
 expect(homeNeuralPlot(panel,{...period,start:null},'RCS08').traces).toEqual([]);
 expect(homeNeuralPlot(panel,{...period,end:null},'RCS08').traces).toEqual([]);
});

test('timestamp conversion accepts known formats and refuses coercion',()=>{
 expect(neuralTime(time)).toBe(time);expect(neuralTime('2026-09-01T19:00:00Z')).toBe(time);
 for(const invalid of [null,undefined,NaN,Infinity,'0','bad','2026-09-01Tbad'])expect(neuralTime(invalid)).toBeNull();
});

test('compact dual axes fit within the container and date window is explicit, Pacific and stable',()=>{
 const compact=homeNeuralLayout(period,342),wide=homeNeuralLayout(period,1200),unset=homeNeuralLayout(period);
 expect(compact.margin.l+compact.margin.r).toBeLessThan(120);expect(compact.xaxis.nticks).toBe(3);
 expect(compact.xaxis.range).toEqual(['2026-09-01 12:00:00','2026-09-01 14:00:00']);
 expect(wide.xaxis.nticks).toBe(7);expect(unset.height).toBe(wide.height);
 expect(compact.yaxis2).toMatchObject({overlaying:'y',side:'right',title:{text:'Stim amp (mA)'}});
 expect(compact.uirevision).toBe(wide.uirevision);expect(compact.hovermode).toBe('closest');
 expect(homeNeuralLayout({...period,start:null}).xaxis.range).toBeUndefined();
 expect(homeNeuralLayout({...period,end:null}).xaxis.range).toBeUndefined();
});


test('contact-pair display uses discrete contacts without changing machine values or numeric power bands',()=>{
 const input={...segment,sensing_contacts:'1-3'};
 const before=JSON.stringify(input);
 const result=homeNeuralPlot({side:'left',segments:[input]},period,'RCS08');
 expect(result.descriptions[0]).toMatchObject({start:time,end:time+7200,source:'R MD Thal',contacts:'1 and 3',center:'20 Hz center',band:'18–22 Hz'});
 expect(result.traces[0].customdata[0][1]).toContain('Sensing contacts: 1 and 3');
 expect(JSON.stringify(input)).toBe(before);
 expect(neuralContactLabel('8 – 10')).toBe('8 and 10');
 expect(neuralContactLabel('1 and 3')).toBe('1 and 3');
 expect(neuralContactLabel('')).toBe('Contacts not recorded');
 expect(neuralContactLabel(null)).toBe('Contacts not recorded');
 expect(neuralSegmentDescription({...input,center_frequency_hz:null},'RCS08').center).toBe('Center frequency not recorded');
 expect(neuralSegmentDescription({...input,center_frequency_hz:null,power_band_label:'23.44 Hz center · band width not recorded'},'RCS08').center).toBe('23.44 Hz center');
});


test('visible interval key includes recordings but omits empty or wholly unavailable settings boundaries',()=>{
 const make=(id,points)=>({...segment,id,points,thresholds:[]});
 const result=plot({segments:[make('empty',[]),make('unknown',[{time,power:null,amplitude:null}]),
  make('conflicting',[{time,power:20,power_conflict:true,amplitude:2,amplitude_conflict:true}]),
  make('power',[{time,power:0,amplitude:null}]),make('amplitude',[{time,power:null,amplitude:0}])]});
 expect(result.descriptions.map(d=>d.id)).toEqual(['power','amplitude']);
 expect(result.observedPower).toBe(1);expect(result.observedAmplitude).toBe(1);
});
