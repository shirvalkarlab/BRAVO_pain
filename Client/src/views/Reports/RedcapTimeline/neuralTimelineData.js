import {escapeText, eventTimeLabel, homeTiming, localTime, settingsSummary} from './data';
import {displayTarget,isRCS08Participant} from 'utils/participantTargets';
import {contactConfiguration} from './contactSchematic';
import {groupState,compareGroupStates} from './neuralGroupState';

export const NEURAL_METRICS = [
  {key:'contacts',label:'Contact configurations',categorical:true},
  {key:'mode',label:'Stimulation mode & cycling',categorical:true},
  {key:'frequency',label:'Frequency',unit:'Hz'},
  {key:'amplitude',label:'Amplitude',unit:'mA'},
  {key:'pulse_width',label:'Pulse width',unit:'µs'},
];
export function quantity(value, unit) {
  const match = String(value ?? '').trim().match(/^([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(Hz|mA|µs|μs|us|s)$/);
  return match && match[2].replace(/[μu]s/,'µs') === unit && Number.isFinite(Number(match[1])) ? Number(match[1]) : null;
}
export function programsAt(event, participant) {
  return ['left','right'].flatMap(side => {
    const programs = new Map();
    for (const row of event.settings?.[side] || []) {
      const match = row.label.match(/^Program (\d+) · (.+)$/);
      const key = match ? match[1] : '';
      if (!programs.has(key)) programs.set(key,{});
      programs.get(key)[match ? match[2] : row.label] = String(row.value ?? '');
    }
    return [...programs].map(([key,rows]) => ({id:`${side}:${key}`,side,rows,
      label:`${displayTarget(participant,side,`${side === 'left' ? 'L' : 'R'} ${rows['Tablet target'] || 'lead'}`)}${key ? ` · Program ${key}` : ''}`}));
  });
}
export function parameterValue(metric, program) {
  const rows = program.rows;
  const label = {frequency:'Frequency',pulse_width:'Pulse width',amplitude:/^running$/i.test(rows['Adaptive state'] || '') ? 'Adaptive amplitude range' : rows['Fixed / paused amplitude'] !== undefined ? 'Fixed / paused amplitude' : 'Amplitude'}[metric.key];
  const raw = rows[label] || 'Not recorded';
  if (label === 'Adaptive amplitude range') {
    const parts = raw.split(/\s+to\s+/i);
    const low = quantity(parts[0],'mA'), high = parts.length === 2 ? quantity(parts[1],'mA') : null;
    return low !== null && high !== null && high >= low ? {low,high,raw,kind:'range'} : {raw,kind:'unresolved'};
  }
  const value = quantity(raw,metric.unit);
  return value === null ? {raw,kind:'unresolved'} : {value,raw,kind:'fixed'};
}

export function knownSegments(start, end, intervals) {
  let segments = start < end ? [[start,end]] : [];
  for (const interval of intervals) {
    const a = localTime(interval.start), b = interval.end === null ? end : localTime(interval.end);
    segments = segments.flatMap(([left,right]) => b <= left || a >= right ? [[left,right]] : [
      ...(a > left ? [[left,a]] : []), ...(b < right ? [[b,right]] : []),
    ]);
  }
  return segments;
}

export function neuralPlot(events, metric, range, participant, unknownIntervals = []) {
  const ordered = events.filter(event => Number.isFinite(event.time)).slice().sort((a,b) => a.time-b.time);
  const start = `${range.start} 00:00:00`, end = `${range.end} 23:59:59`;
  const contactCatalog=new Map();
  const contactEvents=metric.key==='contacts'?ordered.map(event=>{
    const configuration=contactConfiguration(programsAt(event,participant),isRCS08Participant(participant));
    if(!contactCatalog.has(configuration.key))contactCatalog.set(configuration.key,contactCatalog.size+1);
    return {...configuration,number:contactCatalog.get(configuration.key)};
  }):[];
  const series = new Map(), unresolved = [], categories = [], shapes = [], configurations = [], states = new Map();
  ordered.forEach((event,index) => {
    const time = localTime(event.time), next = ordered[index+1] ? localTime(ordered[index+1].time) : end;
    if (time > end || next < start) return;
    const segments = knownSegments(time < start ? start : time,next > end ? end : next,unknownIntervals);
    const observed = time >= start && time <= end && !unknownIntervals.some(gap => event.time >= gap.start && (gap.end === null || event.time < gap.end));
    if (!segments.length && !observed) return;
    const sidePrograms = programsAt(event,participant);
    let categoryValue;
    if(metric.key==='contacts') {
      const configuration=contactEvents[index];
      let position=configurations.findIndex(c=>c.key===configuration.key);
      if(position<0){position=configurations.length;configurations.push(configuration);}
      categoryValue=`C${configuration.number}`;
    } else if(metric.key==='mode') {
      const state=groupState(event.settings);
      states.set(state.label,state); categoryValue=state.label;
    }
    const programs=metric.categorical?[{id:'group',label:metric.label,side:'group',rows:{}}]:sidePrograms;
    const tooltip = `${escapeText(eventTimeLabel(event))}<br>${escapeText(event.label)}<br>${settingsSummary(event.settings,participant)}<br>${homeTiming(event).replace('survey may precede change','observation time does not establish activation')}<br>Click for complete settings`;
    for (const program of programs) {
      const result = metric.categorical?{category:categoryValue}:parameterValue(metric,program);
      const category = result.category || null;
      if (category && !categories.includes(category)) categories.push(category);
      if (result.kind === 'unresolved') {
        unresolved.push({id:event.id,time:localTime(event.time),target:program.label,raw:result.raw});
        continue;
      }
      const values = metric.categorical ? [{key:'',value:categories.indexOf(category)}] : result.kind === 'range'
        ? [{key:'lower limit',value:result.low},{key:'upper limit',value:result.high}] : [{key:'',value:result.value}];
      const color = program.side === 'left' ? '#356E9B' : program.side === 'right' ? '#B16B39' : '#65519A';
      for (const item of values) {
        const key = `${program.id}:${item.key}`;
        if (!series.has(key)) series.set(key,{name:`${program.label}${item.key ? ` · ${item.key}` : ''}`,color,side:program.side,key:item.key,x:[],y:[],customdata:[],mx:[],my:[],mc:[],symbols:[],lastEvent:-2,lastEnd:null});
        const target = series.get(key);
        for (const [left,right] of segments) {
          // Join adjacent known observations with a vertical step. A gap, missing
          // value or absent program leaves the explicit null separator intact.
          if(target.lastEvent===index-1&&target.lastEnd===left){target.x.pop();target.y.pop();target.customdata.pop();}
          target.x.push(left,right,null);target.y.push(item.value,item.value,null);target.customdata.push([event.id,tooltip],[event.id,tooltip],['','']);
          target.lastEvent=index;target.lastEnd=right;
        }
        if (observed) {target.mx.push(time);target.my.push(item.value);target.mc.push([event.id,tooltip]);target.symbols.push(event.time_precision === 'day' ? 'diamond-open' : 'circle');}
      }
      if (result.kind === 'range') for (const [left,right] of segments) shapes.push({type:'rect',xref:'x',yref:'y',x0:left,x1:right,y0:result.low,y1:result.high,fillcolor:color,opacity:0.10,line:{width:0},layer:'below'});
    }
  });
  if(metric.key==='mode'){
    const sorted=[...categories].sort((a,b)=>compareGroupStates(states.get(a),states.get(b)));
    for(const target of series.values()) for(const key of ['y','my'])target[key]=target[key].map(y=>y===null?null:sorted.indexOf(categories[y]));
    categories.splice(0,categories.length,...sorted);
  }
  const hovertemplate = '%{customdata[1]}<extra></extra>';
  const traces = [...series].flatMap(([key,s]) => [
    {type:'scatter',mode:'lines',name:escapeText(s.name),legendgroup:key,x:s.x,y:s.y,customdata:s.customdata,hovertemplate,connectgaps:false,line:{shape:'hv',color:s.color,width:2,dash:s.key ? 'dash' : 'solid'}},
    {type:'scatter',mode:'markers',name:escapeText(s.name),legendgroup:key,showlegend:false,x:s.mx,y:s.my,customdata:s.mc,hovertemplate,marker:{color:s.color,size:7,symbol:s.symbols}},
  ]);
  return {traces,shapes,categories,unresolved,configurations};
}
