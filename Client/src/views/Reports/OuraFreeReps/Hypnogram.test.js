import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Hypnogram, {localTime} from './Hypnogram';

let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));
test('renders exact duration blocks in their proper lanes with unpainted gaps',()=>{
  act(()=>root.render(<Hypnogram sleep={{start:100,end:1100,stages:[{stage:'Awake',start:100,end:101},{stage:'Deep',start:600,end:1100},{stage:'Unknown',start:200,end:300}]}}/>));
  const figure=element.querySelector('[role="img"]');
  expect(figure.getAttribute('aria-label')).toBe('Sleep stages through the night');
  const blocks=figure.querySelectorAll('[title]');
  expect(blocks).toHaveLength(2);
  expect(blocks[0].style.width).toBe('0.1%');expect(blocks[0].style.left).toBe('0%');expect(blocks[0].style.top).toBe('9px');
  expect(blocks[1].style.width).toBe('50%');expect(blocks[1].style.left).toBe('50%');expect(blocks[1].style.top).toBe('141px');
  expect(element.textContent).toContain('Gaps represent missing or excluded samples');
});
test('empty and invalid-duration sessions communicate unavailable eligible stages',()=>{
  for(const sleep of [{start:100,end:200,stages:[]},{start:100,end:100,stages:[{stage:'Deep',start:100,end:200}]}]) {
    act(()=>root.render(<Hypnogram sleep={sleep}/>));
    expect(element.textContent).toContain('No eligible stage samples');
    expect(element.querySelectorAll('[title]')).toHaveLength(0);
  }
});
test('time labels explicitly use Pacific offset across daylight saving changes',()=>{
  expect(localTime(Date.parse('2026-01-02T08:00:00Z')/1000)).toContain('Jan 2');
  expect(localTime(Date.parse('2026-01-02T08:00:00Z')/1000)).toContain('12:00 AM PST');
  expect(localTime(Date.parse('2026-07-02T07:00:00Z')/1000)).toContain('12:00 AM PDT');
});
