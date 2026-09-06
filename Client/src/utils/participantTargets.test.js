/** @jest-environment node */
import {RCS08_PARTICIPANT_ID as id, isRCS08Participant, displayTarget,
  displayTargetText, routeParticipant, currentTarget, currentTargetText} from './participantTargets';

test('only the reviewed participant identity gets the target override', () => {
  [id, 'RCS08', ' rcs08 ', {Id:id}, {id}, {uid:id}, {ParticipantId:id},
    {Name:'RCS08'}, {name:'RCS08'}].forEach(value => expect(isRCS08Participant(value)).toBe(true));
  [null, undefined, 8, {}, [], {Name:'RCS09'}, {Id:8}, 'RCS080', 'RCS09', ''].forEach(value => {
    expect(isRCS08Participant(value)).toBe(false);
    expect(displayTarget(value, 'Left GPi')).toBe('Left GPi');
    expect(displayTargetText(value, 'L GPi · R VIM')).toBe('L GPi · R VIM');
  });
});

test('anatomy labels cover exported side formats without changing source records', () => {
  const record = Object.freeze({Hemisphere:'Left GPi', Target:'GPi', Channel:'L 0-2'});
  ['Left', 'Left GPi', 'LEFT', 'LeftHemisphere', 'HemisphereLocationDef.Left', 'L', 'L_0'].forEach(side =>
    expect(displayTarget(id, side, 'tablet')).toBe('L GPe'));
  ['Right', 'Right VIM', 'RIGHT', 'RightHemisphere', 'HemisphereLocationDef.Right', 'R', 'R_1'].forEach(side =>
    expect(displayTarget(id, side)).toBe('R MD Thal'));
  [null, undefined, '', 'Middle', 'Lower', 'Rostral'].forEach(side =>
    expect(displayTarget(id, side, 'Unknown')).toBe('Unknown'));
  expect(displayTargetText(id, record.Channel)).toBe('L GPe 0-2');
  expect(record).toEqual({Hemisphere:'Left GPi', Target:'GPi', Channel:'L 0-2'});
});

test('display strings retain contact values, units and unrelated terms', () => {
  const text='Left GPi C+2− · Right VIM C+9− · L GPe · R Thal · R MD Thal';
  expect(displayTargetText(id,text)).toBe('L GPe C+2− · R MD Thal C+9− · L GPe · R MD Thal · R MD Thal');
  expect(displayTargetText(id,'LeftHemisphere LFP / Right Hemisphere Amplitude')).toBe('L GPe LFP / R MD Thal Amplitude');
  expect(displayTargetText(id,'L 0⁻2⁺ / R 9-10')).toBe('L GPe 0⁻2⁺ / R MD Thal 9-10');
  expect(displayTargetText(id,'Left STN, Right STN, Left boundary, 55 Hz · 3 mA · 100 µs')).toBe('Left STN, Right STN, Left boundary, 55 Hz · 3 mA · 100 µs');
  expect(displayTargetText(id,null)).toBeNull();
  expect(displayTargetText(id,12)).toBe(12);
});

test('legacy UI wrappers use the active route and cannot leak across participants', () => {
  expect(routeParticipant()).toBeNull();
  expect(routeParticipant(`/reports/redcap-pretrial/${id}`)).toBe(id);
  expect(routeParticipant(`/reports/redcap-pretrial/${id}extra`)).toBeNull();
  expect(routeParticipant('/database')).toBeNull();
  global.window = {location:{pathname:`/participant-overview/${id}`}};
  expect(currentTarget('Left')).toBe('L GPe');
  expect(currentTarget('Right', 'R VIM')).toBe('R MD Thal');
  expect(currentTargetText('L GPi')).toBe('L GPe');
  window.location.pathname='/reports/therapy-history/another-participant';
  expect(currentTarget('Left','Left GPi')).toBe('Left GPi');
  expect(currentTargetText('R VIM')).toBe('R VIM');
  delete global.window;
});
