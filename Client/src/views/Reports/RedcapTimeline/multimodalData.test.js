import {surveyGapTrace,summarySurveyTraces,summaryOuraTraces,summaryEvents,summaryLayout,relayoutRange,hoverTime} from './multimodalData';
const range={start:'2026-08-01',end:'2026-08-07'};
const point=(day,value)=>({time:Date.parse(`${day}T12:00:00-07:00`)/1000,day,value,source:'Reviewed first-party timeline'});
const survey={key:'left_leg_vas_intensity',label:'Left-leg VAS',points:[point('2026-08-01',10),point('2026-08-02',90),point('2026-08-04',20),point('2026-08-05',80),point('2026-08-06',30)]};
const sleep={key:'sleep_total',label:'Total sleep including naps',unit:'hours',points:[point('2026-08-01',8.5),point('2026-08-02',9),point('2026-08-04',7.5),point('2026-08-05',8),point('2026-08-06',9.5)]};
const steps={key:'steps',label:'Steps',unit:'steps',points:[point('2026-08-01',0),point('2026-08-02',1000),point('2026-08-04',2000),point('2026-08-05',3000),point('2026-08-06',4000)]};

test('survey gaps interrupt guides without losing observations, metadata, or mutating the original trace',()=>{
 const trace={x:['2026-08-01 09:00:00','2026-08-01 20:00:00','2026-08-02 23:00:00','2026-08-04 00:00:00'],y:[0,2,3,4],customdata:['a','b','c','d'],line:{color:'red'},connectgaps:true};
 const before=JSON.stringify(trace),result=surveyGapTrace(trace);
 expect(result.y).toEqual([0,2,3,null,4]);expect(result.customdata).toEqual(['a','b','c',null,'d']);expect(result.x[3]).toBeNull();
 expect(result.connectgaps).toBe(false);expect(result.line.color).toBe('red');expect(JSON.stringify(trace)).toBe(before);
 expect(surveyGapTrace({x:[],y:[],customdata:[]}).x).toEqual([]);
});

test('only requested clinical outcomes appear with separate axes and reviewed visit X values preserved with or without medians',()=>{
 const metrics=[survey,{...survey,key:'mpq_standard_0_45',label:'MPQ total',points:[point('2026-08-01',45)]},{...survey,key:'mpq_total',label:'Wrong MPQ score'}];
 const visits={left_leg_vas_intensity:[point('2026-08-03',100)],mpq_standard_0_45:[point('2026-08-03',0)]};
 const original=JSON.stringify({metrics,visits});
 const on=summarySurveyTraces(metrics,visits,[],range,true,[],[]),off=summarySurveyTraces(metrics,visits,[],range,false,[],[]);
 expect(off.map(t=>t.y)).toEqual([[10,90,20,80,30],[100],[45],[0]]);
 expect(off.filter(t=>t.marker.symbol==='x').map(t=>[t.yaxis,t.y])).toEqual([['y',[100]],['y2',[0]]]);
 expect(on.filter(t=>t.mode==='markers')).toEqual(off);
 expect(on.filter(t=>t.mode==='lines')).toHaveLength(2);expect(on.every(t=>t.connectgaps===false)).toBe(true);
 expect(on.some(t=>t.name.includes('Wrong'))).toBe(false);expect(JSON.stringify({metrics,visits})).toBe(original);
 expect(summarySurveyTraces([],{},[],range,true,[],[])).toEqual([]);
});

test('survey medians use full reviewed history before cropping and preserve actual missing days',()=>{
 const whole=summarySurveyTraces([survey],{},[],range,true,[],[]).find(t=>t.mode==='lines');
 const narrow=summarySurveyTraces([survey],{},[],{start:'2026-08-04',end:'2026-08-04'},true,[],[]).find(t=>t.mode==='lines');
 expect(whole.y).toEqual([20,50,null,30,55,30]);expect(narrow.y).toEqual([30]);
 expect(whole.x[2]).toBeNull();
});

test('first-party total sleep values remain hours including naps, Steps remains independent, and missing daily observations stay gaps',()=>{
 const metrics=[steps,sleep,{...sleep,key:'sleep_duration',points:[point('2026-08-01',99999)]}];
 metrics[0]={...steps,points:[...steps.points,point('2026-08-03',null),point('2026-08-07',NaN)]};
 const before=JSON.stringify(metrics);
 const traces=summaryOuraTraces(metrics,range,true,['2026-08-02','2026-08-03']);
 const raw=traces.filter(t=>t.mode==='markers');
 expect(raw[0]).toMatchObject({y:[0,1000,null,2000,3000,4000],yaxis:'y',connectgaps:false});
 expect(raw[1]).toMatchObject({y:[8.5,9,null,7.5,8,9.5],yaxis:'y2'});
 expect(raw[1].hovertemplate).toContain('hours');expect(raw[1].x[0]).toBe('2026-08-01 12:00:00');
 expect(raw[0].marker.symbol[1]).toBe('x');expect(raw[0].marker.size[1]).toBe(10);expect(raw[0].marker.symbol[0]).toBe('circle');
 expect(raw[0].customdata[1]).toContain('Stimulation-visit day');expect(raw[0].customdata[0]).not.toContain('Stimulation-visit day');
 expect(traces[1].customdata[0]).toContain('Centered median');
 expect(summaryOuraTraces(metrics,range,false,['2026-08-02','2026-08-03'])).toEqual(raw);
 expect(JSON.stringify(metrics)).toBe(before);expect(summaryOuraTraces([],range,true,[])).toEqual([]);
 const narrow=summaryOuraTraces(metrics,{start:'2026-08-04',end:'2026-08-04'},true,[]);
 expect(narrow[1].y).toEqual([2000]);expect(narrow[3].y).toEqual([8.5]);
});

test('local calendar filters transitions inclusively and renumbers only visible events without source mutation',()=>{
 const events=[{id:'before',time:Date.parse('2026-08-01T06:59:59Z')/1000},{id:'start',time:Date.parse('2026-08-01T07:00:00Z')/1000},{id:'last',time:Date.parse('2026-08-08T06:59:59Z')/1000},{id:'after',time:Date.parse('2026-08-08T07:00:00Z')/1000}];
 expect(summaryEvents(events,range).map(e=>[e.id,e.number])).toEqual([['start',1],['last',2]]);expect(events[1].number).toBeUndefined();
});

test('shared layout respects clinical limits, responsive axes and zoom while preserving concise stimulation hover',()=>{
 const events=[{id:'first',number:1,time:point('2026-08-02',0).time,label:'Observed home settings',kind:'settings_observed',settings:{group:[],left:[],right:[]}}];
 const opts={range,left:'VAS',right:'MPQ',events,limits:[[0,100],[0,45]]};
 const compact=summaryLayout({...opts,width:342}),wide=summaryLayout({...opts,width:1000,xRange:['a','b']}),auto=summaryLayout({...opts,width:0,limits:null,events:[]});
 expect(compact.yaxis.range).toEqual([0,100]);expect(compact.yaxis2).toMatchObject({range:[0,45],overlaying:'y',side:'right'});
 expect(compact.xaxis.range).toEqual(['2026-08-01 00:00:00','2026-08-07 23:59:59']);expect(wide.xaxis.range).toEqual(['a','b']);
 expect(compact.xaxis.nticks).toBe(3);expect(wide.xaxis.nticks).toBe(7);expect(compact.margin.l+compact.margin.r).toBeLessThan(120);
 expect(compact.annotations[0]).toMatchObject({name:'first',text:'1',captureevents:true});expect(compact.annotations[0].hovertext).toContain('activation time not established');
 expect(compact.shapes).toHaveLength(1);expect(auto.shapes).toEqual([]);expect(auto.yaxis.rangemode).toBe('tozero');expect(auto.yaxis2.rangemode).toBe('tozero');
 expect(compact.uirevision).toBe(wide.uirevision);expect(compact.hovermode).toBe('closest');
});

test('zoom messages distinguish shared reset, complete ranges and unrelated updates; numeric hover timestamps preserve Plotly date clock',()=>{
 expect(relayoutRange({'xaxis.autorange':true})).toBeNull();expect(relayoutRange({'xaxis.range':['a','b']})).toEqual(['a','b']);
 expect(relayoutRange({'xaxis.range[0]':'a','xaxis.range[1]':'b'})).toEqual(['a','b']);
 expect(relayoutRange({'xaxis.range[0]':'a'})).toBeUndefined();expect(relayoutRange({'xaxis.range[1]':'b'})).toBeUndefined();expect(relayoutRange({width:300})).toBeUndefined();
 expect(hoverTime('2026-08-01 12:00:00')).toBe('2026-08-01 12:00:00');expect(hoverTime(Date.parse('2026-08-01T12:00:00Z'))).toBe('2026-08-01 12:00:00.000');
});
