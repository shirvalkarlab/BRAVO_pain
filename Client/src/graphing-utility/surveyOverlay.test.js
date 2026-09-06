import {surveyOverlaySeries, clearSurveyOverlayAxes} from './surveyOverlay';

test('native and linked survey overlays preserve zero/timestamps and omit missing or invalid values', () => {
  const form = [{questions: [{type: 'score', text: 'NRS'}, {type: 'redcapForm', text: 'VAS'},
    {type: 'redcapForm', text: 'Time'}, {type: 'score', text: 'Hidden', show: false}]}];
  const records = [
    {Date: 100, Result: [[0, '2.5', 100, 8]]},
    {Date: 200, Result: [[null, '', 200, 9]]},
    {Date: 300, Result: [[5, 'invalid', 300, 10]]},
    {Date: 400, Result: [[Infinity, '  ', 400, 11]]},
    {Date: 500, Result: []},
  ];
  const result = surveyOverlaySeries({form, records});
  expect(result.map(s => s.name)).toEqual(['NRS', 'VAS']);
  expect(result[0].y).toEqual([0, 5]);
  expect(result[0].x.map(d => d.getTime())).toEqual([100000, 300000]);
  expect(result[1].y).toEqual([2.5]);
  expect(surveyOverlaySeries({})).toEqual([]);
});

test('overlay cleanup keeps neural axes intact and is safe to repeat', () => {
  const base = {ylayout: 'yaxis'}, overlay = {ylayout: 'yaxis3', surveyOverlay: true};
  const fig = {ax: [base, overlay], layout: {yaxis: {range: [0, 10]}, yaxis3: {}}, gca: overlay};
  clearSurveyOverlayAxes(fig); clearSurveyOverlayAxes(fig);
  expect(fig.ax).toEqual([base]);
  expect(fig.layout).toEqual({yaxis: {range: [0, 10]}});
  expect(fig.gca).toBe(base);
});

test('incomplete forms and missing eligible observations do not create empty overlays',()=>{
  expect(surveyOverlaySeries()).toEqual([]);
  expect(surveyOverlaySeries({form:null})).toEqual([]);
  expect(surveyOverlaySeries({records:{}})).toEqual([]);
  const form=[{}, {questions:[{type:'score',text:'Pain'},{type:'text',text:'Comment'}]}];
  const records=[{Date:NaN,Result:[[],[2,'text']]},{Date:1},{Date:2,Result:[[],[false]]}];
  expect(surveyOverlaySeries({form,records})).toEqual([]);
  const fig={ax:[],layout:{}};
  clearSurveyOverlayAxes(fig);
  expect(fig.ax).toEqual([]);
});
