import {groupState,compareGroupStates} from './neuralGroupState';

const rows = input => Object.entries(input).map(([label,value])=>({label,value}));
const settings = (mode='Open loop / fixed stimulation',cycle='Off',left={},right={}) => ({
  group:rows({'Mode at observation':mode,Cycling:cycle}),left:rows(left),right:rows(right),
});
const adaptive = (state='Running',threshold='Dual threshold direct') => ({'Adaptive state':state,'Threshold mode':threshold});

test('explicit group fixed mode and cycling off establish no-cycling state without inferring delivery',()=>{
  const source=settings(undefined,undefined,{'Amplitude':'0 mA','Adaptive state':'Not configured'});
  expect(groupState(source)).toEqual({label:'Open loop / fixed · No cycling',order:[0]});
  expect(groupState(settings('Open loop',' OFF '))).toEqual({label:'Open loop / fixed · No cycling',order:[0]});
  expect(groupState(settings('Fixed stimulation'))).toEqual({label:'Open loop / fixed · No cycling',order:[0]});
  expect(groupState(settings('Open loop / fixed'))).toEqual({label:'Open loop / fixed · No cycling',order:[0]});
});

test.each([
  [undefined,'Group mode not recorded'],[null,'Group mode not recorded'],['','Group mode not recorded'],
  ['Not recorded','Group mode not recorded'],['unknown','Group mode not recorded'],['NA','Group mode not recorded'],
  ['Unexpected','Group mode not recognized · Unexpected'],
])('unknown group authority is never inferred from adaptive configuration: %p',(mode,label)=>{
  const source=settings('Closed loop','Off',adaptive());
  source.group[0].value=mode;
  expect(groupState(source)).toEqual({label,order:[9]});
});

test('missing structures and null row values remain unknown without mutation or crashes',()=>{
  expect(groupState()).toEqual({label:'Group mode not recorded',order:[9]});
  expect(groupState(null)).toEqual({label:'Group mode not recorded',order:[9]});
  expect(groupState({group:rows({'Mode at observation':null}),left:rows({'Adaptive state':null})})).toEqual({label:'Group mode not recorded',order:[9]});
});

test.each([
  ['On · on 60 s / off 300 s',[1,1,5],'1 min','5 min'],
  ['On · on .5 s / off +60. s',[1,0.5/60,1],'0.00833333 min','1 min'],
  ['On · on 1 min / off 500 ms',[1,1,500/60000],'1 min','0.00833333 min'],
  ['On · on 120 seconds / off 120000 milliseconds',[1,2,2],'2 min','2 min'],
  ['On · on 2 minutes / off 1 second',[1,2,1/60],'2 min','0.0166667 min'],
  ['On · on 60 sec / off 0 s',[1,1,0],'1 min','0 min'],
])('explicit duration units convert to numeric minutes: %s',(cycle,order,on,off)=>{
  expect(groupState(settings(undefined,cycle))).toEqual({label:`Open loop / fixed · Cycling on ${on} / off ${off}`,order});
});

test.each([
  ['On · on Not recorded / off 60 s','not recorded','1 min'],
  ['On · on 60 s / off Not recorded','1 min','not recorded'],
  ['On · on -1 s / off 2 Hz','not recorded','not recorded'],
  ['On · on 1e2 s / off Infinity s','not recorded','not recorded'],
  ['On · on 1 s (note); export: 2 s / off 3 s','not recorded','0.05 min'],
  [`On · on ${'9'.repeat(400)} s / off 60 s`,'not recorded','1 min'],
  ['On','not recorded','not recorded'],
])('missing or ambiguous durations remain independent and sort after known settings: %s',(cycle,on,off)=>{
  expect(groupState(settings(undefined,cycle))).toEqual({label:`Open loop / fixed · Cycling on ${on} / off ${off}`,order:[9]});
});

test.each(['Not recorded','Unknown','',null,'On with unknown layout'])('missing or unrecognized cycling never becomes cycling off: %p',cycle=>{
  expect(groupState(settings(undefined,cycle))).toEqual({label:'Open loop / fixed · Cycling not recorded',order:[9]});
});

test('paused programs remain fixed; threshold configuration alone does not imply running',()=>{
  expect(groupState(settings('Open loop','Off',adaptive('Suspended')))).toEqual({label:'Adaptive paused / fixed · No cycling',order:[0]});
  expect(groupState(settings('Open loop','Off',adaptive('Paused')))).toEqual({label:'Adaptive paused / fixed · No cycling',order:[0]});
  expect(groupState(settings('Open loop','Off',{'Threshold mode':'Dual threshold direct'}))).toEqual({label:'Open loop / fixed · No cycling',order:[0]});
});

test.each([
  ['Single threshold',{label:'Closed loop · single threshold',order:[2,0]}],
  ['Single_threshold_direct',{label:'Closed loop · single threshold',order:[2,0]}],
  ['Dual threshold',{label:'Closed loop · dual threshold',order:[2,1]}],
  ['DUAL-THRESHOLD-DIRECT',{label:'Closed loop · dual threshold',order:[2,1]}],
])('known adaptive threshold modes use group rows and normalized program fields: %s',(threshold,expected)=>{
  expect(groupState(settings('Closed loop','Off',adaptive('Running',threshold)))).toEqual(expected);
});

test('mixed running and paused sides preserve a consistent group threshold mode and never mutate sources',()=>{
  const source=settings('Closed loop','Off',{
    'Program 1 · Adaptive state':'Running','Program 1 · Threshold mode':'Dual threshold direct',
    'Program 2 · Adaptive state':'Suspended','Program 2 · Threshold mode':'Dual threshold direct',
    'Program 2 · Fixed / paused amplitude':'0 mA','Program 2 · Sensing source hemisphere':'Right',
  },adaptive('Paused'));
  const before=JSON.stringify(source);
  expect(groupState(source)).toEqual({label:'Closed loop · dual threshold',order:[2,1]});
  expect(JSON.stringify(source)).toBe(before);
});

test.each([
  [settings('Closed loop','Off',adaptive(),adaptive('Paused','Single threshold direct')),'different threshold modes'],
  [settings('Open loop','On · on 60 s / off 60 s',adaptive('Paused')),'Cycling and configured adaptive therapy'],
  [settings('Open loop','Off',adaptive()),'Group mode is open loop'],
  [settings('Closed loop','Off',adaptive('Paused')),'no recorded adaptive program is running'],
  [settings('Closed loop','Off',adaptive('Suspended'),{'Adaptive state':'Not configured'}),'no recorded adaptive program is running'],
  [settings('Closed loop','On'),'Closed-loop group also records cycling'],
  [settings('Closed loop','Off',adaptive('Running','Single threshold inverse')),'sensing-only'],
])('contradictory group evidence remains visibly conflicted (%#)',(source,reason)=>{
  const result=groupState(source);
  expect(result.order).toEqual([10]);
  expect(result.warning).toContain(reason);
  expect(result.label).toBe(`Conflicting settings · ${result.warning}`);
});

test.each([
  [settings('Closed loop','Not recorded',adaptive()),'Closed loop · Cycling not recorded'],
  [settings('Closed loop','Off'),'Closed loop · Threshold mode not recorded'],
  [settings('Closed loop','Off',{'Adaptive state':'Unknown'}),'Closed loop · Threshold mode not recorded'],
  [settings('Closed loop','Off',adaptive('Running','Not recorded')),'Closed loop · Threshold mode not recorded'],
  [settings('Closed loop','Off',adaptive(),{'Adaptive state':'Paused'}),'Closed loop · Threshold mode not recorded'],
  [settings('Closed loop','Off',adaptive('Running','Novel threshold')),'Closed loop · Threshold mode not recognized: novel threshold'],
])('incomplete adaptive evidence stays unknown rather than inferred (%#)',(source,label)=>{
  expect(groupState(source)).toEqual({label,order:[9]});
});

test('sort uses numeric ON then OFF minutes, never lexical duration ordering',()=>{
  const states=[
    groupState(settings('Closed loop','Off',adaptive())),
    groupState(settings('Open loop','On · on 600 s / off 60 s')),
    groupState(settings('Open loop','On · on 120 s / off 600 s')),
    groupState(settings('Open loop','On · on 120 s / off 60 s')),
    groupState(settings('Closed loop','Off',adaptive('Running','Single threshold'))),
    groupState(settings()),groupState(),
    groupState(settings('Closed loop','On')),
  ];
  expect(states.sort(compareGroupStates).map(state=>state.order)).toEqual([[0],[1,2,1],[1,2,10],[1,10,1],[2,0],[2,1],[9],[10]]);
  expect(compareGroupStates({label:'A',order:[0]},{label:'B',order:[0,0]})).toBeLessThan(0);
  expect(compareGroupStates({label:'B',order:[0,0]},{label:'A',order:[0]})).toBeGreaterThan(0);
  expect(compareGroupStates({label:'Same',order:[1]},{label:'Same',order:[1]})).toBe(0);
});
