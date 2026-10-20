/** @jest-environment node */
import {displayTarget, displayTargetText, routeParticipant, currentTarget, currentTargetText} from './participantTargets';

test.each(['synthetic-a', 'synthetic-b', null, {Name:'synthetic-a'}, {uid:'synthetic-id'}])('identity %p never supplies anatomical evidence', participant => {
  expect(displayTarget(participant,'Left','Recorded left lead')).toBe('Recorded left lead');
  expect(displayTarget(participant,'Right')).toBe('Right');
  expect(displayTargetText(participant,'L GPi 0-2 · R STN 8-10')).toBe('L GPi 0-2 · R STN 8-10');
});

test('source values and missing labels are retained without coercion or mutation',()=>{
  const record=Object.freeze({hemisphere:'Left',label:'Recorded lead'});
  expect(displayTarget('synthetic',record.hemisphere,record.label)).toBe(record.label);
  expect(displayTarget('synthetic',undefined)).toBeUndefined();
  expect(displayTarget('synthetic','Left',null)).toBeNull();
  expect(displayTargetText('synthetic',null)).toBeNull();
  expect(displayTargetText('synthetic',12)).toBe(12);
  expect(record).toEqual({hemisphere:'Left',label:'Recorded lead'});
});

test('legacy display wrappers cannot infer anatomy from browser routes',()=>{
  expect(routeParticipant()).toBeNull();
  expect(routeParticipant('/reports/redcap-pretrial/synthetic-a')).toBeNull();
  global.window={location:{pathname:'/participant-overview/synthetic-a'}};
  expect(currentTarget('Left')).toBe('Left');
  expect(currentTarget('Right','Recorded right lead')).toBe('Recorded right lead');
  expect(currentTargetText('L GPi')).toBe('L GPi');
  delete global.window;
});
