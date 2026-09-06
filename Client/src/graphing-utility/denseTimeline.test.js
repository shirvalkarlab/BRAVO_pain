import { mergeDenseLineSeries, mergeAnnotationSeries } from "./denseTimeline";

test("dense traces preserve all points and separate recording boundaries", () => {
  const line=(x,y)=>({type:'lineseries',axName:'heart',options:{id:'heart'},x,y});
  const a=line([1,2],[0,4]), b=line([5,6],[7,8]);
  const other={type:'scatter',axName:'survey',x:[4],y:[0]};
  const result=mergeDenseLineSeries([a,other,b],3);
  expect(result).toHaveLength(2);
  expect(result[0].x).toEqual([1,2,null,5,6,null]);
  expect(result[0].y).toEqual([0,4,null,7,8,null]);
  expect(result[0].options.type).toBe('scattergl');
  expect(result[0].options.connectgaps).toBe(false);
  expect(result[1]).toBe(other);
  expect(a.x).toEqual([1,2]);
  expect(mergeDenseLineSeries([a,b],10)).toEqual([a,b]);
});

test('annotation batching preserves every marker timestamp and ID and keeps labels distinct',()=>{
  const event=(id,name,time)=>({type:'annotations',axName:'LFP',options:{id,name,color:'green'},x:[time,time],y:[0,50000]});
  const input=[event('a','event',10),event('b','event',20),event('c','other',30)];
  const output=mergeAnnotationSeries(input,1);
  expect(output).toHaveLength(2);
  expect(output[0].x).toEqual([10,10,null,20,20,null]);
  expect(output[0].y).toEqual([0,50000,null,0,50000,null]);
  expect(output[0].options.customdata).toEqual(['a','a',null,'b','b',null]);
  expect(output[0].options.type).toBe('scattergl');
  expect(output[1]).toBe(input[2]);
  expect(input[0].x).toEqual([10,10]);
});

test('default thresholds keep small traces and non-event intervals intact',()=>{
  const line={type:'lineseries',axName:'neural',options:{id:'neural'},x:[1,2],y:[0,null]};
  const interval={type:'shading',axName:'all',options:{id:'testing'},x:[1,2],y:[0,1]};
  const point={type:'annotations',axName:'all',options:{id:'event'},x:[3,3],y:[0,1]};
  expect(mergeDenseLineSeries([line])[0]).toBe(line);
  const result=mergeAnnotationSeries([interval,point]);
  expect(result[0]).toBe(interval);
  expect(result[1]).toBe(point);
});
