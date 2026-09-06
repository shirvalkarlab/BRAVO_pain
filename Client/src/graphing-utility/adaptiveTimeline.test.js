import {adaptiveParameters, amplitudeRangePercent} from './adaptiveTimeline';
const note = limits => ({Adaptive:{StimulationConfiguration:{Type:'Medtronic Adaptive'}, RecordingConfiguration:{Config:{Thresholds:{AmplitudeThreshold:limits,LFPThresholds:[30,50]}}}}});
test('only valid adaptive ranges produce a percentage, retaining zero and gaps',()=>{
  const limits=adaptiveParameters(note([0,4])).StimulationLimits;
  expect([0,2,4,null,undefined,NaN,-1,5].map(v=>amplitudeRangePercent(v,limits))).toEqual([0,50,100,null,null,null,null,null]);
  for(const value of [null,{},note([0,0]),note([2,2]),note([3,1]),note([-1,2])]) expect(adaptiveParameters(value).StimulationLimits).toBeUndefined();
  expect(amplitudeRangePercent(2,undefined)).toBeNull();
});
test('reads nested thresholds without mutating source metadata',()=>{
  const value=note([1,3]); value.Adaptive.RecordingConfiguration.Config.Thresholds.LFPThresholds=[{Value:[50,50]}];
  const before=JSON.stringify(value);
  expect(adaptiveParameters(value)).toEqual({StimulationLimits:[1,3],LFPThresholds:[50]});
  expect(JSON.stringify(value)).toBe(before);
});

test('nominal or invalid sensing thresholds are not presented as measured adaptive settings',()=>{
  for (const lfp of [[20,30],[20,50],[50,30],undefined,[NaN,50],[null]]) {
    const value=note([0,4]);
    value.Adaptive.RecordingConfiguration.Config.Thresholds.LFPThresholds=lfp;
    const result=adaptiveParameters(value);
    expect(result.LFPThresholds).toBeUndefined();
    expect(result.StimulationLimits).toEqual([0,4]);
  }
  const value=note([0,4]);
  value.Adaptive.StimulationConfiguration.Type='Medtronic Open Loop';
  expect(adaptiveParameters(value).StimulationLimits).toBeUndefined();
  expect(amplitudeRangePercent(2,[3,1])).toBeNull();
});
