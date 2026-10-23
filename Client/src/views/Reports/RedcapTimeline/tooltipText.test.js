import {tooltipText, metricTraces, settingsSummary, homeTiming} from './data';
import {NO_VERIFIED_HOME_ASSIGNMENT} from './settingDisplay';
import {ouraTraces, sampleTraces} from './ouraData';
import {conditionSummary, stimulationAxisSettings, medicationTimeline} from './comparisonData';
import {neuralHoverLines} from './homeNeuralChartData';

const time=Date.parse('2026-04-05T19:00:00Z')/1000;
const range={start:'2026-04-05',end:'2026-04-05'};
const text=html=>{const node=document.createElement('div');node.innerHTML=html.replace(/<br>/g,' ');return node.textContent;};
const widths=html=>html.split('<br>').map(line=>{const node=document.createElement('div');node.innerHTML=line;return node.textContent.length;});

test('plain context wraps complete words, blank lines and long tokens without losing text',()=>{
 const html=tooltipText(NO_VERIFIED_HOME_ASSIGNMENT);
 expect(html).toContain('<br>');expect(text(html)).toBe(NO_VERIFIED_HOME_ASSIGNMENT);
 expect(Math.max(...widths(html))).toBeLessThanOrEqual(42);
 expect(tooltipText('')).toBe('');expect(tooltipText('First\r\nSecond\nThird')).toBe('First<br>Second<br>Third');
 const token='abcdefghijklmnopqrstuvxyz0123456789'.repeat(4);
 expect(tooltipText(token).replace(/<br>/g,'')).toBe(token);
 expect(Math.max(...widths(tooltipText(token)))).toBeLessThanOrEqual(42);
});

test('source markup stays literal, every word and unit survives, and entities remain intact',()=>{
 const source=`${'A long source context with full words '.repeat(3)}<img onerror="bad"> & 'quoted' 55 Hz · 2.5 mA · 100 µs`;
 const html=tooltipText(source),node=document.createElement('div');node.innerHTML=html;
 expect(node.querySelector('img')).toBeNull();expect(node.querySelector('script')).toBeNull();
 expect(html).toContain('&lt;img');expect(html).toContain('&amp;');expect(html).toContain('&#39;quoted&#39;');
 expect(text(html)).toBe(source);expect(Math.max(...widths(html))).toBeLessThanOrEqual(42);
});

test('observed, rolling and visit pain contexts bound source uncertainty without changing scores',()=>{
 const phase='A synthetic phase label long enough to need wrapping while retaining its full name';
 const reason='Conflicting observations leave activation unverified; <source> remains literal & complete.';
 const metric={label:'Synthetic pain',points:[{time,value:1,phase:'a'},{time:time+60,value:5,phase:'a'}]};
 const before=JSON.stringify(metric);
 const traces=metricTraces(metric,[{key:'a',label:phase}],range,true,[{time:time+30,value:3,phase:'a'}],[],true,[{start:time,end:null,reason}]);
 expect(traces.map(trace=>trace.y)).toEqual([[1,5],[3,3,3],[3]]);
 for(const trace of traces)for(const html of trace.customdata){
  expect(text(html)).toContain(phase);expect(text(html)).toContain(NO_VERIFIED_HOME_ASSIGNMENT);expect(text(html)).toContain(reason);
  expect(Math.max(...widths(html))).toBeLessThanOrEqual(42);expect(html).not.toContain('<source>');
 }
 expect(JSON.stringify(metric)).toBe(before);
});

test('daily and timed Oura keep full assignment limits and center-time qualifications',()=>{
 const daily=ouraTraces({label:'Daily',unit:'steps',points:[{day:range.start,value:123}]},range,[],true,false);
 expect(daily.map(trace=>trace.y)).toEqual([[123],[123]]);
 for(const trace of daily){expect(text(trace.customdata[0])).toContain('daily totals are not assigned to an active program.');expect(Math.max(...widths(trace.customdata[0]))).toBeLessThanOrEqual(42);}
 const source='A long stored source label with <literal> text and retained provenance qualifiers';
 const sampled=sampleTraces({label:'Timed',unit:'bpm',points:[{time,value:65,source}]},range,[],false,true);
 expect(sampled.map(trace=>trace.y)).toEqual([[65],[65]]);
 expect(text(sampled[0].customdata[0][1])).toBe(source);expect(text(sampled[0].customdata[0][2])).toBe(NO_VERIFIED_HOME_ASSIGNMENT);
 expect(text(sampled[1].hovertemplate)).toContain('settings describe the center timestamp.');
 const event={time:time-3600,time_precision:'day'};
 expect(text(homeTiming(event,{time},'reading may precede change'))).toContain('reading may precede change.');
 expect(text(homeTiming(event,{time},'observation time does not establish activation'))).toContain('observation time does not establish activation.');
});

test('full settings, ganged scope and medication notes retain units, text and exact dates',()=>{
 const note='This synthetic medication note includes <literal> context & carefully qualified historical evidence.';
 const settings={left:[{label:'Stimulation contacts',value:'C+2−'},{label:'Frequency',value:'55 Hz'},{label:'Amplitude',value:'2.5 mA'},{label:'Pulse width',value:'100 µs'},{label:'Custom source context',value:note}],right:[]};
 const before=JSON.stringify(settings),summary=settingsSummary(settings,'synthetic');
 for(const fragment of ['55 Hz','2.5 mA','100 µs',note])expect(text(summary)).toContain(fragment);
 expect(Math.max(...widths(summary))).toBeLessThanOrEqual(42);expect(JSON.stringify(settings)).toBe(before);
 const condition={label:'Synthetic CL',mode:'closed_loop',settings:[{label:'Left contacts',value:'C+2−'},{label:'Left adaptive status',value:'RUNNING'},{label:'Left ganged to',value:'Right'},{label:'Left lower lfp threshold (LSB)',value:'0'},{label:'Left upper lfp threshold (LSB)',value:'155'}]};
 const controller=stimulationAxisSettings(condition,'synthetic');
 expect(text(controller)).toContain('LFP thresholds: lower 0 · upper 155 LSB');expect(text(controller)).toContain('sensing values above are recorded for');
 expect(Math.max(...widths(controller))).toBeLessThanOrEqual(42);
 const medication={id:'synthetic',name:'Synthetic medicine',drug_class:'Class',dose:'5 mg',note,start:time,end:time+60};
 const plot=medicationTimeline([medication],range.end,time,[],time+120);
 expect(text(plot.traces[0].hovertemplate)).toContain(note);expect(text(plot.traces[0].hovertemplate)).toContain('this is a coverage limit, not a medication stop date');
 expect(plot.traces[0].x).toEqual(['2026-04-05 12:00:00','2026-04-05 12:01:00']);
 const summaryHtml=conditionSummary({label:'Synthetic',settings:[{label:'Qualified source text',value:note}]});
 expect(text(summaryHtml)).toContain(note);expect(Math.max(...widths(summaryHtml))).toBeLessThanOrEqual(42);
 expect(neuralHoverLines([note])).toBe(tooltipText(note));
});
