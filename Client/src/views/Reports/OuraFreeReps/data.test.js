import {aggregatePoints, calendarSeries, defaultRange, filterPoints, pairDays, pearsonR, stageBlocks} from './data';

const p = (day, value) => ({day, value});

test('date bounds are inclusive, optional, and preserve true zero while excluding nonfinite values', () => {
  const rows = [p('2026-05-01', 1), p('2026-05-02', 0), p('2026-05-03', 3), p('2026-05-04', null), p('2026-05-05', NaN), p('2026-05-06', Infinity)];
  expect(filterPoints(rows, '2026-05-02', '2026-05-03')).toEqual(rows.slice(1, 3));
  expect(filterPoints(rows, '', '')).toEqual(rows.slice(0, 3));
  expect(filterPoints(rows, '', '2026-05-02')).toEqual(rows.slice(0, 2));
  expect(filterPoints(rows, '2026-05-03', '')).toEqual([rows[2]]);
  expect(filterPoints(rows, '2026-05-03', '2026-05-01')).toEqual([]);
});

test('weekly and monthly means count only observed finite days, crossing calendar boundaries correctly', () => {
  const rows = [p('2026-06-01', 8), p('2026-05-31', 6), p('2026-05-25', 0), p('2026-05-26', null), p('2026-05-24', 9)];
  expect(aggregatePoints(rows, 'week')).toEqual([
    {day:'2026-05-18', value:9, count:1}, {day:'2026-05-25', value:3, count:2}, {day:'2026-06-01', value:8, count:1},
  ]);
  expect(aggregatePoints(rows, 'month')).toEqual([{day:'2026-05-01', value:5, count:3}, {day:'2026-06-01', value:8, count:1}]);
  expect(aggregatePoints(rows, 'day')).toEqual([
    {day:'2026-05-24', value:9, count:1}, {day:'2026-05-25', value:0, count:1}, {day:'2026-05-31', value:6, count:1}, {day:'2026-06-01', value:8, count:1},
  ]);
  expect(aggregatePoints([], 'month')).toEqual([]);
});

test('daily plotting introduces an explicit missing gap without synthesizing measurements', () => {
  const rows = [p('2026-05-01', 0), p('2026-05-02', 2), p('2026-05-09', 5)];
  expect(calendarSeries(rows)).toEqual([rows[0], rows[1], p('2026-05-03', null), rows[2]]);
  expect(calendarSeries([])).toEqual([]);
  expect(rows).toHaveLength(3);
});

test('comparison matches exact Oura days and excludes missing values on either side', () => {
  expect(pairDays([p('a', 0), p('b', 2), p('c', null), p('d', 4), p('e', NaN)],
    [p('a', 3), p('b', Infinity), p('c', 8), p('e', 10), p('f', 12)]))
    .toEqual([{day:'a', x:0, y:3}]);
});

test('Pearson agrees with a hand-calculated centered-sums oracle, including large common offsets', () => {
  // x=[1,2,3,4], y=[2,1,4,3]: covariance sum=3, x/y squared-deviation sums=5.
  const pairs = [2,1,4,3].map((y,i) => ({x:i+1, y}));
  expect(pearsonR(pairs)).toBeCloseTo(0.6, 12);
  expect(pearsonR(pairs.map(({x,y}) => ({x:x+1e9,y:y+1e9})))).toBeCloseTo(0.6, 12);
  expect(pearsonR([0,1,2].map(x => ({x,y:-2*x})))).toBe(-1);
  expect(pearsonR([0,1,2].map(x => ({x,y:2*x})))).toBe(1);
});

test('correlation is unavailable for insufficient, constant, nonfinite or numerically overflowing pairs', () => {
  expect(pearsonR([])).toBeNull();
  expect(pearsonR([{x:1,y:1},{x:2,y:2}])).toBeNull();
  expect(pearsonR([1,2,3].map(y => ({x:1,y})))).toBeNull();
  expect(pearsonR([1,2,3].map(x => ({x,y:2})))).toBeNull();
  expect(pearsonR([{x:NaN,y:1},{x:2,y:2},{x:3,y:3}])).toBeNull();
  expect(pearsonR([1e200,2e200,3e200].map(x=>({x,y:x})))).toBeNull();
});

test('sleep blocks clip to boundaries, preserve tiny widths and leave excluded gaps empty', () => {
  const stages = [
    {stage:'Awake',start:90,end:110}, {stage:'REM',start:120,end:121}, {stage:'Light',start:150,end:170}, {stage:'Deep',start:190,end:210},
    {stage:'Unknown',start:120,end:140}, {stage:'Deep',start:160,end:160}, {stage:'Light',start:50,end:100}, {stage:'REM',start:200,end:230},
  ];
  expect(stageBlocks(stages, 100, 200)).toEqual([
    {...stages[0],left:0,width:10,lane:0}, {...stages[1],left:20,width:1,lane:1},
    {...stages[2],left:50,width:20,lane:2}, {...stages[3],left:90,width:10,lane:3},
  ]);
  expect(stageBlocks([{stage:'Awake',start:100,end:100.1}],100,200)[0].width).toBeCloseTo(0.1);
  expect(stageBlocks(stages,200,200)).toEqual([]);
  expect(stageBlocks(stages,200,100)).toEqual([]);
  expect(stageBlocks([],100,200)).toEqual([]);
});

test('default range is ninety inclusive calendar days ending on latest observed day, not today', () => {
  expect(defaultRange([])).toEqual({start:'',end:''});
  expect(defaultRange([{points:[]}])).toEqual({start:'',end:''});
  expect(defaultRange([{points:[p('2026-01-01',2),p('2026-05-31',3)]},{points:[p('2026-03-20',4)]}]))
    .toEqual({start:'2026-03-03',end:'2026-05-31'});
});
