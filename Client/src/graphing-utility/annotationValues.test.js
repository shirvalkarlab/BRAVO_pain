import { annotationValues } from './annotationValues';

test('point events do not scan data or invent a summary window',()=>{
  const inaccessible=new Proxy([],{get(){throw new Error('Data should not be read');}});
  expect(annotationValues(inaccessible,{Date:2,Duration:0},'score')).toEqual([]);
  expect(annotationValues(inaccessible,{Date:2},'score')).toEqual([]);
});

test('interval summaries retain zero and strict time boundaries, omitting missing/category values',()=>{
  const data=[{ChannelNames:['score'],Time:[1,2,3,4,5,6,7],Data:[[8,0,null,4,'awake',Infinity,9]]}];
  expect(annotationValues(data,{Date:1,Duration:6},'score')).toEqual([0,4]);
});

test('other channels and unavailable channel payloads contribute no values',()=>{
  const data=[{ChannelNames:['Other'],Time:[2],Data:[[999]]},{ChannelNames:['score'],Time:[2]},
    {ChannelNames:['score'],Time:[2],Data:[null]},{ChannelNames:['score'],Time:[2],Data:[[0]]}];
  expect(annotationValues(data,{Date:1,Duration:2},'score')).toEqual([0]);
});
