import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import HomeNeuralData from './HomeNeuralData';
import {RCS08_PARTICIPANT_ID} from 'utils/participantTargets';
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
const mount=async()=>act(async()=>root.render(<HomeNeuralData participant={RCS08_PARTICIPANT_ID}/>));
const click=async(text)=>{const button=[...element.querySelectorAll('button')].find(n=>n.textContent===text);expect(button).toBeDefined();await act(async()=>button.click());};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockQuery={data:{windows:[window('current'),window('previous')]},loading:false,error:''};element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});
test('four ordered panels identify stimulated sides and preserve original data under current and previous visits',async()=>{
 await mount();expect([...element.querySelectorAll('[data-panel]')].map(x=>x.dataset.panel)).toEqual(['current:left','current:right','previous:left','previous:right']);
 expect(element.textContent).toContain('10 minutes');expect(element.textContent).toContain('opposite side');
 expect(element.textContent).toContain('L GPe · biomarker');expect(element.textContent).toContain('R MD Thal · biomarker');
 expect(element.textContent).not.toContain('rolling median');expect(element.querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
 expect(mockProps).toEqual([RCS08_PARTICIPANT_ID,0]);await click('Refresh neural view');expect(mockProps[1]).toBe(1);
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
 expect(element.querySelector('input[role="combobox"]').value).toContain('R MD Thal');
 expect(element.querySelector('input[role="combobox"]').value).toContain('13.67 Hz center');
});
