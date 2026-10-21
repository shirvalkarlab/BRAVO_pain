import {summaryNeuralGroups, summaryNeuralPlot} from './summaryNeuralData';

const t = Date.parse('2026-10-06T00:00:00-07:00') / 1000;
const point = (offset,power,amplitude) => ({time:t+offset,power,amplitude});
const segment = (id,start,end,points) => ({id,start:t+start,end:t+end,points});
const historical = {id:'historical',start:t,end:t+86400,panels:[{side:'left',segments:[segment('source',0,86400,[point(600,20,1)])]}]};
const observed = {id:'recent',display_basis:'recorded_observations',start:t+86400,end:t+3*86400,panels:[{side:'left',segments:[segment('source',86400,3*86400,[point(86400+600,30,null)])],amplitude_series:[point(86400+300,null,0),point(2*86400,null,2)]}]};
const values = (plot,axis) => plot.traces.filter(trace=>trace.mode==='lines+markers'&&trace.yaxis===axis).flatMap(trace=>trace.y).filter(Number.isFinite);

test('groups both collections by side and gives repeated source intervals distinct display IDs without changing input',()=>{
 const data={windows:[historical],observation_windows:[observed]},before=JSON.stringify(data);
 const groups=summaryNeuralGroups(data);
 expect(groups).toHaveLength(1);expect(groups[0].parts.map(part=>part.period)).toEqual([historical,observed]);
 expect(new Set(groups[0].segments.map(s=>s.id)).size).toBe(2);
 const plot=summaryNeuralPlot(groups[0],'SYNTHETIC');
 expect(values(plot,'y')).toEqual([20,30]);expect(values(plot,'y2')).toEqual([1,0,2]);
 expect(plot.observedPower).toBe(2);expect(plot.observedAmplitude).toBe(3);expect(plot.latestTime).toBe(t+2*86400);
 expect(plot.traces.filter(trace=>trace.yaxis==='y')).toHaveLength(2); // No guide between periods.
 expect(plot.descriptions.map(d=>d.id)).toEqual(groups[0].segments.map(s=>s.id));
 expect(JSON.stringify(data)).toBe(before);
});

test('missing collections, panels and settings do not invent observations; unknown display bases are ignored',()=>{
 expect(summaryNeuralGroups()).toEqual([]);expect(summaryNeuralGroups({windows:[{}],observation_windows:[{display_basis:'other'}]})).toEqual([]);
 const groups=summaryNeuralGroups({windows:[{...historical,panels:[{side:'left'}, {side:'right',segments:[{id:'no-points',start:t,end:t+86400}]}]}]});
 expect(groups.map(g=>g.side)).toEqual(['left','right']);expect(groups[1].segments[0].id).toBe('no-points');
 expect(summaryNeuralPlot(groups[0])).toEqual({traces:[],descriptions:[],observedPower:0,observedAmplitude:0,latestTime:null});
 expect(summaryNeuralPlot(groups[1]).traces).toEqual([]);
});

test('identical repeated samples are counted once, zero current stays zero and different values are not silently adjudicated',()=>{
 const repeated={...historical,display_basis:'recorded_observations'};
 const data={windows:[historical],observation_windows:[repeated,{...repeated,panels:[{side:'left',segments:[segment('changed',0,86400,[point(600,21,1),point(1200,null,0)])]}]}]};
 const plot=summaryNeuralPlot(summaryNeuralGroups(data)[0]);
 expect(values(plot,'y')).toEqual([20,21]);expect(values(plot,'y2')).toEqual([1,0]);
 expect(plot.observedPower).toBe(2);expect(plot.observedAmplitude).toBe(2);
 expect(plot.latestTime).toBe(t+1200);
});

test('deduplication uses UTC instants and metric values, not rounded display dates or the other lead',()=>{
 const first=Date.parse('2026-11-01T01:30:00-07:00')/1000,second=Date.parse('2026-11-01T01:30:00-08:00')/1000;
 const period={start:first,end:second+3600,panels:['left','right'].map(side=>({side,segments:[],amplitude_series:[{time:first,amplitude:0},{time:second,amplitude:0}]}))};
 const plots=summaryNeuralGroups({windows:[period]}).map(group=>summaryNeuralPlot(group));
 expect(plots.map(plot=>plot.observedAmplitude)).toEqual([2,2]);expect(plots[0].latestTime).toBe(second);
});

test('clipped, invalid or conflicting values cannot hide a later valid observation or fabricate a settings interval',()=>{
 const invalid={...historical,panels:[{side:'left',segments:[
   segment('before',0,300,[point(600,20,1)]),
   {...segment('invalid',0,86400,[point(600,20,1)]),start:null},
   {...segment('invalid-end',0,86400,[point(600,20,1)]),end:null},
   segment('outside',0,86400,[point(-1,5,1),point(86400,6,1),{time:'bad',power:10,amplitude:2},{...point(600,20,1),power_conflict:true,amplitude_conflict:true}]),
 ]}]};
 const plot=summaryNeuralPlot(summaryNeuralGroups({windows:[invalid,historical]})[0]);
 expect(values(plot,'y')).toEqual([20]);expect(values(plot,'y2')).toEqual([1]);expect(plot.descriptions).toHaveLength(1);
 for (const missing of ['start','end']) {
   const noWindow={...historical,[missing]:null};
   expect(summaryNeuralPlot(summaryNeuralGroups({windows:[noWindow,historical]})[0]).observedPower).toBe(1);
 }
});

test('independent current ignores embedded amplitude and preserves missing-bin breaks and source metadata uncertainty',()=>{
 const period={...observed,panels:[{...observed.panels[0],segments:[{...observed.panels[0].segments[0],
   points:[point(86400+600,30,99)],sensing_provenance:{status:'unverified',metadata_available:false},
 }],amplitude_series:[point(86400+300,null,0),point(86400+300,null,0),point(86400+900,null,null),point(86400+1500,null,2)]}]};
 const plot=summaryNeuralPlot(summaryNeuralGroups({observation_windows:[period]})[0]);
 expect(values(plot,'y2')).toEqual([0,2]);expect(values(plot,'y2')).not.toContain(99);
 expect(plot.traces.find(trace=>trace.yaxis==='y2').y).toEqual([0,null,null,2]);
 expect(plot.traces.find(trace=>trace.yaxis==='y2').customdata.every(value=>value[0]===null)).toBe(true);
 expect(plot.descriptions[0].schedule).toContain('Unverified');
});

test.each([
 ['sensing_contacts','0-2','1-3'],
 ['center_frequency_hz',12,20],
 ['sensing_side','left','right'],
 ['settings',{group:[{label:'Group',value:'A'}]},{group:[{label:'Group',value:'B'}]}],
 ['sensing_provenance',{status:'recorded'},{status:'unverified'}],
 ['evidence','First source record','Separate source record'],
])('equal values retain distinct %s provenance while identical full observations appear once',(field,first,second)=>{
 const withSource=value=>({...historical,panels:[{...historical.panels[0],segments:[{...historical.panels[0].segments[0],[field]:value}]}]});
 const original=withSource(first),changed=withSource(second);
 const plot=summaryNeuralPlot(summaryNeuralGroups({windows:[original,changed],observation_windows:[{...original,display_basis:'recorded_observations'}]})[0]);
 expect(values(plot,'y')).toEqual([20,20]);expect(values(plot,'y2')).toEqual([1,1]);
 expect(plot.descriptions).toHaveLength(2);expect(plot.observedPower).toBe(2);
});

test('point-level source evidence and independent-current provenance are retained for equal values',()=>{
 const parts=['export-A','export-B','export-A'].map(source=>({...historical,panels:[{side:'left',
   segments:[{...historical.panels[0].segments[0],points:[{...point(600,20,1),source}]}],
   amplitude_series:[point(600,null,0)],amplitude_provenance:source,
 }]}));
 const plot=summaryNeuralPlot(summaryNeuralGroups({windows:parts})[0]);
 expect(values(plot,'y')).toEqual([20,20]);expect(values(plot,'y2')).toEqual([0,0]);
 expect(plot.descriptions).toHaveLength(2);
});
