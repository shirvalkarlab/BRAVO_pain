import {chartLayout} from './chartLayout';

test('narrow Oura plots preserve the data area and allocate space for a stacked legend',()=>{
  const traces=Array.from({length:6},(_,i)=>({name:`Trace ${i}`}));
  const small=chartLayout(390,traces,290,'Day','Score'),wide=chartLayout(1100,traces,290,'Day','Score');
  expect(390-small.margin.l-small.margin.r).toBeGreaterThanOrEqual(300);
  expect(small.height-small.margin.t-small.margin.b).toBeGreaterThanOrEqual(200);
  expect(small.legend.orientation).toBe('v');
  expect(wide.legend.orientation).toBe('h');
  expect(small.xaxis.nticks).toBeLessThan(wide.xaxis.nticks);
  expect(small.width).toBeUndefined();
  expect(small.height).toBeGreaterThan(wide.height);
});

test('single traces retain their height and no legend; hidden traces do not reserve legend rows',()=>{
  expect(chartLayout(390,[{}],290,'Day','Score')).toMatchObject({height:290,showlegend:false});
  expect(chartLayout(390,[{showlegend:false},{showlegend:false}],290,'Day','Score').margin.b).toBe(70);
});
