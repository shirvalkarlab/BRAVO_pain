import { categoricalIntervals, categoricalSegments } from "./categoricalIntervals";

test("preserves exact category transitions, duration and gaps", () => {
  const result = categoricalIntervals([0, 60, 120, 300, 360], [60, 60, 60, 60, 30], ['rest','rest','active','active','rest']);
  expect(result.x).toEqual([120000,60000,60000,30000]);
  expect(result.y).toEqual(['rest','active','active','rest']);
  expect(result.base.map(d=>d.getTime())).toEqual([0,120000,300000,360000]);
});

test("a long unchanged state needs one bar without losing duration", () => {
  const times=Array.from({length:200000},(_,i)=>i*60);
  const result=categoricalIntervals(times,60,times.map(()=> 'rest'));
  expect(result.x).toEqual([200000*60000]);
  expect(result.y).toEqual(['rest']);
});

test("dense rendering uses separate segments with exact endpoints", () => {
  const input=categoricalIntervals([10,20,40],[10,10,5],['rest','active','rest']);
  const segments=categoricalSegments(input);
  expect(segments.x.map(d=>d===null?null:d.getTime())).toEqual([10000,20000,null,20000,30000,null,40000,45000,null]);
  expect(segments.y).toEqual(['rest','rest',null,'active','active',null,'rest','rest',null]);
});
