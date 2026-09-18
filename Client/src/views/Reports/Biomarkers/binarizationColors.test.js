import {diverging, divergingRgb, BIN_HI_RGB, BIN_LO_RGB} from './binarizationModel';
test('heatmap colors center correlation at zero and AUC at chance with clamped endpoints', () => {
  expect(BIN_HI_RGB).toEqual([213,94,0]);expect(BIN_LO_RGB).toEqual([0,114,178]);
  expect(divergingRgb(-2,0,1)).toEqual(BIN_LO_RGB);expect(divergingRgb(2,0,1)).toEqual(BIN_HI_RGB);
  expect(divergingRgb(0,0,1)).toEqual([255,255,255]);expect(divergingRgb(.5,.5,.5)).toEqual([255,255,255]);
  expect(divergingRgb(.25,.5,.5)).toEqual([127.5,184.5,216.5]);
  expect(diverging(.25,.5,.5)).toBe('rgb(128,185,217)');expect(diverging('1',.5,.5)).toBe('rgb(213,94,0)');
  for (const missing of [null,undefined,NaN,Infinity,'not numeric']) expect(diverging(missing,0,1)).toBe('#e9e9e9');
});
