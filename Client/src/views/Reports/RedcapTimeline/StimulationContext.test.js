import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import StimulationContext from './StimulationContext';
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children})=><span>{children}</span>}));

const event={id:'a',kind:'settings_observed',number:1,time:Date.parse('2026-08-01T19:00:00Z')/1000,label:'Group <B> snapshot',evidence:'Observed in JSON; onset unknown',settings:{
  group:[{label:'Group',value:'Group B'},{label:'Mode',value:'Adaptive'}],
  left:[{label:'Amplitude',value:'1.5 mA'},{label:'Frequency',value:'130 Hz'},{label:'Contacts',value:'0− / case+'}],
  right:[{label:'Pulse width',value:'60 µs'},{label:'Sensing',value:'8–12 Hz'},{label:'Status',value:'Not recorded'}],
}};
let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});
const render=async(props)=>act(async()=>root.render(<StimulationContext {...props}/>));

test('no recorded events shows a clear empty state and does not invent settings',async()=>{
  await render({events:[],onSelect:jest.fn()});
  expect(element.textContent).toContain('No home-program transitions are established');
  expect(element.querySelector('dl')).toBeNull();expect(element.querySelector('[role="combobox"]')).toBeNull();
});

test('shared group and separate left/right cards retain exact units, context caveats and literal untrusted text',async()=>{
  const onDetailsChange=jest.fn();
  const props={events:[event],selected:event,onSelect:jest.fn(),previous:{...event,label:'Prior state'},limited:false,onDetailsChange};
  await render(props);
  expect(element.textContent).toContain('Group settings · shared by both sides');
  expect(element.textContent).toContain('Left · stimulation and sensing');expect(element.textContent).toContain('Right · stimulation and sensing');
  const rows=[...element.querySelectorAll('dl')].map(dl=>[...dl.querySelectorAll('dd')].map(dd=>dd.textContent));
  expect(rows).toEqual([['Group B','Adaptive'],['1.5 mA','130 Hz','0− / case+'],['60 µs','8–12 Hz','Not recorded']]);
  expect(element.textContent).toContain('Group <B> snapshot');expect(element.querySelector('B')).toBeNull();
  expect(element.textContent).toContain('2026-08-01 12:00:00 Pacific');expect(element.textContent).toContain('Observed in JSON; onset unknown');
  expect(element.textContent).toContain('does not establish continuous delivery');
  const summary=element.querySelector('.MuiAccordionSummary-root');expect(summary.getAttribute('aria-expanded')).toBe('false');
  await act(async()=>summary.click());expect(onDetailsChange).toHaveBeenCalledWith(true);
  await render({...props,openDetails:true});expect(summary.getAttribute('aria-expanded')).toBe('true');
  await act(async()=>summary.click());expect(onDetailsChange).toHaveBeenLastCalledWith(false);
});

test('explicit record selection opens its details, dropdown works and an overcrowded range explains the cap',async()=>{
  const next={...event,id:'b',number:2,label:'Second snapshot',settings:{group:[],left:[],right:[]}};
  const selected=jest.fn();
  await render({events:[event,next],selected:next,onSelect:selected,limited:true,openDetails:true});
  expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
  expect(element.textContent).toContain('2 records fall in this window');expect(element.textContent).toContain('up to 12');
  expect(element.querySelectorAll('dt')).toHaveLength(0);
  const selector=element.querySelector('input[role="combobox"]');
  await act(async()=>{selector.focus();selector.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));});
  const option=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.endsWith(event.label));
  await act(async()=>option.dispatchEvent(new MouseEvent('click',{bubbles:true})));
  expect(selected).toHaveBeenCalledWith('a');
});

test('search renders at most 100 matches but finds later records by full timestamp, label and number',async()=>{
  const events=Array.from({length:150},(_,i)=>({...event,id:`record-${i}`,number:i+1,label:`Snapshot ${i}`,time:event.time+i}));
  events[149]={...events[149],kind:'stimulation_status',label:'Unique adaptive change',time:Date.parse('2026-08-05T19:45:00Z')/1000};
  const onSelect=jest.fn();await render({events,selected:events[0],onSelect,limited:true});
  expect(element.textContent).toContain('Showing up to 100 matches');expect(element.textContent).toContain('these 150 records');
  const input=element.querySelector('input[role="combobox"]');
  await act(async()=>{input.focus();input.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));});
  expect(document.querySelectorAll('[role="option"]')).toHaveLength(100);
  for (const query of ['2026-08-05 12:45:00','Unique adaptive','150.']) {
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,query);input.dispatchEvent(new Event('input',{bubbles:true}));});
    const options=[...document.querySelectorAll('[role="option"]')];expect(options).toHaveLength(1);expect(options[0].textContent).toContain('Unique adaptive change');
  }
  await act(async()=>document.querySelector('[role="option"]').dispatchEvent(new MouseEvent('click',{bubbles:true})));
  expect(onSelect).toHaveBeenCalledWith('record-149');
});

test('a date-only change is labeled with unknown time throughout the selector and details',async()=>{
  const day={...event,time:Date.parse('2026-09-03T07:00:00Z')/1000,time_precision:'day'};
  await render({events:[day],selected:day,onSelect:jest.fn(),openDetails:true,onDetailsChange:jest.fn()});
  expect(element.textContent).toContain('2026-09-03 · time not recorded');expect(element.textContent).not.toContain('00:00:00');
  expect(element.querySelector('input').value).toContain('2026-09-03 · time not recorded');
});

test.each(['https://example.org/reviewed-source','http://example.org/insecure','javascript:alert(1)',undefined])('reviewed source links appear only for HTTPS (%s)',async(source_url)=>{
  const selected={...event,source_url};
  await render({events:[selected],selected,onSelect:jest.fn(),openDetails:true,onDetailsChange:jest.fn()});
  const link=element.querySelector('a');
  if (source_url?.startsWith('https://')) {
    expect(link.textContent).toBe('Reviewed source');expect(link.getAttribute('href')).toBe(source_url);
    expect(link.getAttribute('target')).toBe('_blank');expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  } else expect(link).toBeNull();
});

test.each([['81b245ec31594d9894f1dfc9438b6348','Target','L GPe','R MD Thal'],['other-participant','Tablet target','Left GPi','Right VIM']])(
 'target and sensing labels follow the reviewed participant mapping without changing source settings (%s)',async(uid,targetLabel,left,right)=>{
  const original=window.location.pathname;
  window.history.replaceState({},'',`/reports/redcap-pretrial/${uid}`);
  const selected={...event,settings:{group:[],left:[{label:'Tablet target',value:'Left GPi'}],right:[{label:'Tablet target',value:'Right VIM'},{label:'Sensing source hemisphere',value:'Left'}]}};
  const before=JSON.stringify(selected);
  try {
    await render({events:[selected],selected,onSelect:jest.fn(),openDetails:true,onDetailsChange:jest.fn()});
    expect([...element.querySelectorAll('dt')].map(x=>x.textContent)).toEqual([targetLabel,targetLabel,'Sensing source hemisphere']);
    expect([...element.querySelectorAll('dd')].map(x=>x.textContent)).toEqual([left,right,uid==='other-participant'?'Left':'L GPe']);
    expect(JSON.stringify(selected)).toBe(before);
  } finally {window.history.replaceState({},'',original);}
 });
