import {therapyLayout,impedanceLayout,groupLabel} from './plotLayout';

test('group display names hide device enum prefixes without changing identities',()=>{
  const ids=['GroupIdDef.GROUP_A','GroupIdDef.GROUP_B','GroupIdDef.GROUP_C','GroupIdDef.GROUP_D','Custom group'];
  expect(ids.map(groupLabel)).toEqual(['Group A','Group B','Group C','Group D','Custom group']);
  expect(ids[0]).toBe('GroupIdDef.GROUP_A');
});

test('therapy timeline uses fewer date ticks at 390px while preserving a useful plot and slider area',()=>{
  const small=therapyLayout(390,400),wide=therapyLayout(1100,500);
  expect(390-small.margin.l-small.margin.r).toBeGreaterThan(280);
  expect(small.height-small.margin.t-small.margin.b).toBeGreaterThanOrEqual(240);
  expect(small.xaxis.nticks).toBe(4);
  expect(wide.xaxis.nticks).toBeGreaterThan(small.xaxis.nticks);
  expect(small.xaxis.tickformat).toContain('<br>');
  expect(small.width).toBeUndefined();
  expect(therapyLayout(0).height).toBe(400);
});

test('impedance hemispheres stack at narrow widths and return side by side on desktop',()=>{
  const small=impedanceLayout(390,420),wide=impedanceLayout(1100,420);
  expect([small.rows,small.columns]).toEqual([2,1]);
  expect([wide.rows,wide.columns]).toEqual([1,2]);
  expect(small.rows*small.columns).toBe(2);
  expect(small.layout.height).toBeGreaterThan(wide.layout.height);
  expect(390-small.layout.margin.l-small.layout.margin.r).toBeGreaterThanOrEqual(320);
  expect(small.ticks.tickangle).toBe(0);
  expect(small.layout.width).toBeUndefined();
  expect(impedanceLayout(0).layout.height).toBe(420);
});
