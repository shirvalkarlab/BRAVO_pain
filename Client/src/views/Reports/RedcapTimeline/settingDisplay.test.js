import {settingValueLabel,NO_VERIFIED_HOME_ASSIGNMENT} from './settingDisplay';

test.each([
  [undefined,'Not recorded'],[{},'Not recorded'],[{value:null},'Not recorded'],[{value:'NA'},'Not recorded'],
  [{label:'Group',value:'GroupIdDef.GROUP_A'},'Group A'],[{label:'Group',value:'Custom group'},'Custom group'],
  [{label:'Amplitude control',value:'CURRENT'},'Current'],[{label:'Amplitude control',value:'VOLTAGE'},'VOLTAGE'],
  [{label:'Left sensing status',value:'ENABLED'},'Enabled'],[{label:'Sensing status',value:'DISABLED'},'Disabled'],[{label:'Sensing status',value:'OTHER'},'OTHER'],
  [{label:'Adaptive status',value:'RUNNING'},'Running'],[{label:'Adaptive state',value:'PAUSED'},'Paused'],[{label:'Adaptive state',value:'SUSPENDED'},'Suspended'],[{label:'Adaptive state',value:'NOT_CONFIGURED'},'Not configured'],[{label:'Adaptive state',value:'OTHER'},'OTHER'],
  [{label:'Left adaptive mode',value:'SINGLE_THRESHOLD_DIRECT'},'Single threshold direct'],[{label:'Threshold mode',value:'DUAL_THRESHOLD_DIRECT'},'Dual threshold direct'],[{label:'Threshold mode',value:'SINGLE_THRESHOLD_INVERSE'},'Single threshold inverse'],[{label:'Threshold mode',value:'OTHER'},'OTHER'],
  ...Object.entries({ZERO_AND_ONE:'0 and 1',ZERO_AND_TWO:'0 and 2',ZERO_AND_THREE:'0 and 3',ONE_AND_TWO:'1 and 2',ONE_AND_THREE:'1 and 3',TWO_AND_THREE:'2 and 3'}).map(([value,expected])=>[{label:'Sensing contacts',value:`SensingElectrodeConfigDef.${value}`},expected]),
  [{label:'Sensing channel',value:'CUSTOM'},'CUSTOM'],[{value:0},'0'],[{label:'Frequency',value:'55 Hz'},'55 Hz'],
])('known enum presentation preserves source values and unknown codes (%j)',(row,expected)=>{
  const before=JSON.stringify(row);expect(settingValueLabel(row)).toBe(expected);expect(JSON.stringify(row)).toBe(before);
});

test('missing home assignment directs the reader to source snapshots without implying interval activation',()=>{
 expect(NO_VERIFIED_HOME_ASSIGNMENT).toContain('No verified home-program assignment for this time');
 expect(NO_VERIFIED_HOME_ASSIGNMENT).toContain('snapshot does not establish active settings at this time');
});
