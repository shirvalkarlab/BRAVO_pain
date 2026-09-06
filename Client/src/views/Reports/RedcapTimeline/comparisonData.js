import {trialPhaseBands} from './trialPhases';
import {escapeText, localTime} from './data';
import {displayTarget,displayTargetText} from 'utils/participantTargets';

const PALETTE=['#35669B','#99723A','#6F5599','#317C71','#A65364','#687842'];
const finitePoints=condition=>condition.points.filter(point=>Number.isFinite(point.value)&&Number.isFinite(point.time));

export function surveyCount(condition) {
  const points=finitePoints(condition);
  return `n = ${points.length} surveys (${new Set(points.map(point=>localTime(point.time).slice(0,10))).size} days)`;
}

export function comparisonCoverage(provenance,medications=false) {
  const source=provenance || {},parts=[];
  if(medications&&Number.isFinite(source.source_rows)) parts.push(`${source.source_rows.toLocaleString()} documented medication source rows.`);
  if(Number.isFinite(source.source_max_survey)) parts.push(`${medications?'Reviewed surveys extend through':'Matching source contains surveys through'} ${localTime(source.source_max_survey)} Pacific.`);
  if(Number.isFinite(source.matched)&&Number.isFinite(source.canonical_rows)) {
    const unmatched=Number.isFinite(source.unmatched_canonical)?source.unmatched_canonical:source.canonical_rows-source.matched;
    parts.push(`Matched ${source.matched.toLocaleString()} of ${source.canonical_rows.toLocaleString()} reviewed surveys; ${unmatched.toLocaleString()} unmatched surveys are excluded from condition comparisons.`);
  }
  if(medications&&Number.isFinite(source.regimens_without_complete_interval)) parts.push(`${source.regimens_without_complete_interval.toLocaleString()} regimens lack a complete interval and are excluded from condition comparisons.`);
  return parts.join(' ') || 'Source coverage details are not available.';
}

export function compactLabel(label) {
  const text=String(label);
  const short=text.length>48?`${text.slice(0,45)}…`:text;
  return (short.match(/.{1,24}(?:\s|$)|.{1,24}/g) || ['']).map(part=>escapeText(part.trim())).join('<br>');
}

export function topPrograms(metric,mode) {
  const ids=metric.top?.[mode] || [];
  return metric.conditions.filter(condition=>ids.includes(condition.id)&&condition.count>=5&&finitePoints(condition).length>=5)
    .sort((a,b)=>a.median-b.median).slice(0,3);
}

export function conditionSummary(condition) {
  const rows=condition.settings || [];
  const medication=['drug_class','status','dose','frequency','route','timing','background'];
  const details=[...rows.map(row=>`${condition.mode==='open_loop'&&/threshold/i.test(row.label)?`Stored ${row.label} (not controlling stimulation)`:row.label}: ${row.value}`),...medication.filter(key=>condition[key]).map(key=>`${key.replace('_',' ')}: ${condition[key]}`)];
  const lines=[];
  for(let i=0;i<details.length;i+=2) lines.push(details.slice(i,i+2).map(escapeText).join(' · '));
  return [`<b>${escapeText(condition.label)}</b>`,...lines].join('<br>');
}

export function conditionPlot(metric,conditions,horizontal=false) {
  const traces=[];
  conditions.forEach((condition,index)=>{
    const points=finitePoints(condition),color=PALETTE[index%PALETTE.length];
    const values=points.map(point=>point.value),positions=points.map(()=>index);
    const summary=conditionSummary(condition);
    const axes=horizontal?{x:values,y:positions}:{x:positions,y:values};
    traces.push({type:'box',...axes,orientation:horizontal?'h':'v',name:condition.label,boxpoints:false,width:0.55,
      line:{color,width:2},fillcolor:`rgba(${[1,3,5].map(at=>parseInt(color.slice(at,at+2),16)).join(',')},0.15)`,opacity:1,showlegend:false,
      hovertemplate:`${summary}<br>n=${condition.count} · median=${condition.median}<extra></extra>`});
    const jitter=points.map((_,i)=>index+((i*37%101)/100-0.5)*0.32);
    const dots=horizontal?{x:values,y:jitter}:{x:jitter,y:values};
    traces.push({type:'scatter',...dots,mode:'markers',name:condition.label,marker:{color,size:6,opacity:0.68},showlegend:false,
      customdata:points.map(point=>[localTime(point.time),point.value]),
      hovertemplate:`<b>${escapeText(metric.label)}: %{customdata[1]:.1f}</b><br>%{customdata[0]} Pacific<br>${summary}<extra></extra>`});
  });
  const ticks=conditions.map((condition,index)=>`${index+1}. ${compactLabel(condition.label)}<br>n=${condition.count} · median ${condition.median}`);
  const category={tickmode:'array',tickvals:conditions.map((_,i)=>i),ticktext:ticks,automargin:true,range:[-0.65,conditions.length-0.35],zeroline:false};
  const score={title:{text:`Score (${metric.range.join('–')})`,font:{size:17}},range:metric.range,automargin:true,zeroline:false,gridcolor:'#edf0f4'};
  // Draw medians above the individual points, including zero-IQR boxes and
  // medians that coincide with a quartile. Only the fill is translucent.
  const medians=conditions.map((condition,index)=>({type:'line',name:'Condition median',xref:'x',yref:'y',layer:'above',
    line:{color:'#172B4D',width:3},...(horizontal
      ?{x0:condition.median,x1:condition.median,y0:index-0.275,y1:index+0.275}
      :{x0:index-0.275,x1:index+0.275,y0:condition.median,y1:condition.median})}));
  return {traces,layout:{height:horizontal?Math.max(350,conditions.length*55+120):420,
    shapes:medians,
    margin:{l:horizontal?230:65,r:30,t:20,b:horizontal?75:145},
    xaxis:horizontal?score:category,yaxis:horizontal?{...category,autorange:'reversed'}:score}};
}

export function finalizedProgram(metric,reference,mode='open_loop',label='Finalized OL') {
  if(!reference?.available||!reference.id||reference.mode!==mode) return null;
  const matched=metric.conditions.find(condition=>condition.id===reference.id&&condition.mode===mode);
  return {...reference,...(matched || {count:0,median:null,points:[]}),label,settings:reference.settings};
}

const recorded=value=>value!==undefined&&value!==null&&!/^(?:NA|not recorded|unknown|)$/i.test(String(value).trim())?String(value):null;
const fieldsFrom=rows=>new Map((rows || []).map(row=>[row.label,recorded(row.value)]));
const thresholdMode=value=>{
  const mode=recorded(value);
  if(!mode) return 'Mode: not recorded';
  // The device explicitly records the threshold mode; cycling is independent.
  return `Mode: ${mode.replace(/^.*\./,'').replace(/_/g,' ').toLowerCase().replace(/^./,letter=>letter.toUpperCase())}`;
};
const compactContacts=value=>(value || 'Contacts not recorded').replace(/Case\+|c\+/gi,'C+').replace(/,\s*/g,'');
const sensingContacts=(value,side)=>{
  if(!value) return 'contacts not recorded';
  const numbers={ZERO:0,ONE:1,TWO:2,THREE:3};
  const contacts=String(value).split(/[._\s]+/).filter(word=>Object.prototype.hasOwnProperty.call(numbers,word));
  return contacts.length===2?contacts.map(word=>numbers[word]+(side==='Right'?8:0)).join('–'):value;
};
const sourceSide=(value,fallback)=>/^(?:.*\.)?left$/i.test(value || '')?'left':/^(?:.*\.)?right$/i.test(value || '')?'right':fallback;
const targetName=(participant,side,fallback)=>displayTarget(participant,side,fallback || (side==='left'?'L':'R'));

function homeSettingLines(condition,participant) {
  const home=condition.home_settings,groups=fieldsFrom(home.group),lines=[];
  const cycling=groups.get('Cycling');
  if(cycling&&condition.mode!=='closed_loop') lines.push(cycling==='Off'?'Continuous stimulation':`Cycling ${cycling}`);
  for(const side of ['left','right']) {
    if(!home[side]?.length) continue;
    const fields=fieldsFrom(home[side]);
    const target=targetName(participant,side,fields.get('Tablet target')?`${side==='left'?'L':'R'} ${fields.get('Tablet target')}`:null);
    lines.push(`${target} ${compactContacts(fields.get('Stimulation contacts'))}`);
    const running=/^running$/i.test(fields.get('Adaptive state'));
    const amplitude=running?fields.get('Adaptive amplitude range'):fields.get('Amplitude') || fields.get('Fixed / paused amplitude');
    lines.push(`${fields.get('Frequency') || 'Frequency not recorded'} · ${amplitude || 'Amplitude not recorded'} · ${fields.get('Pulse width') || 'Pulse width not recorded'}`);
    if(condition.mode==='closed_loop') {
      lines.push(thresholdMode(fields.get('Threshold mode')));
      const sensingSide=sourceSide(fields.get('Sensing source hemisphere'),side);
      const sensingTarget=targetName(participant,sensingSide);
      lines.push(`BrainSense ${sensingTarget}: ${fields.get('Sensing contacts') || 'contacts not recorded'} · ${fields.get('Biomarker center frequency') || 'frequency not recorded'}`);
      const lower=fields.get('Lower LFP threshold'),upper=fields.get('Upper LFP threshold');
      lines.push(`LFP thresholds: lower ${lower || 'not recorded'} · upper ${upper || 'not recorded'}`);
      if(fields.get('Adaptive state')) lines.push(`Adaptive state: ${fields.get('Adaptive state')}`);
    }
  }
  return lines;
}

export function stimulationSettingLines(condition,participant) {
  if(condition.home_settings) return homeSettingLines(condition,participant);
  const settings=fieldsFrom(condition.settings),value=key=>settings.get(key);
  const number=key=>{const raw=value(key);return raw!==null&&raw!==undefined&&Number.isFinite(Number(raw))?Number(raw):null;};
  const duration=key=>{const seconds=number(key);return seconds===null?'?':seconds>=60&&seconds%60===0?`${seconds/60} min`:`${seconds} s`;};
  const cycle=value('Cycle'),lines=[];
  if(cycle==='On') lines.push(`${duration('cycle on sec')} ON / ${duration('cycle off sec')} OFF`);
  else if(cycle==='Off'&&condition.mode!=='closed_loop') lines.push('Continuous stimulation');
  for(const side of ['Left','Right']) {
    const contacts=value(`${side} contacts`);
    if(!contacts) continue;
    const target=targetName(participant,side.toLowerCase(),value(`${side} target`));
    lines.push(`${target} ${compactContacts(contacts)}`);
    const frequency=number(`${side} rate hz`),width=number(`${side} pulse width us`),amplitude=number(`${side} amplitude mA`);
    const lower=number(`${side} lower limit mA`),upper=number(`${side} upper limit mA`);
    const adaptive=condition.mode==='closed_loop'&&value(`${side} adaptive status`)?.toUpperCase()==='RUNNING';
    const current=adaptive?(lower!==null&&upper!==null&&upper>=lower?`${lower}–${upper}`:null):amplitude;
    lines.push(`${frequency===null?'?':frequency} Hz · ${current===null?'?':current} mA · ${width===null?'?':width} µs`);
    if(condition.mode==='closed_loop') {
      lines.push(thresholdMode(value(`${side} adaptive mode`)));
      // These legacy fields are the recorded per-channel values. Keep their scope
      // explicit when a ganged controller is reported; never borrow other values.
      const sensing=value(`${side} sensing channel`),frequency=number(`${side} sensing frequency hz`);
      lines.push(`BrainSense ${target}: ${sensingContacts(sensing,side)} · ${frequency===null?'frequency not recorded':`${frequency} Hz`}`);
      lines.push(`LFP thresholds: lower ${value(`${side} lower lfp threshold (LSB)`) || 'not recorded'} · upper ${value(`${side} upper lfp threshold (LSB)`) || 'not recorded'} LSB`);
      const ganged=value(`${side} ganged to`);
      if(ganged&&!/none|not.ganged/i.test(ganged)) lines.push(`Ganged to: ${targetName(participant,sourceSide(ganged,side.toLowerCase()),ganged)} (sensing values above are recorded for ${target})`);
      if(value(`${side} adaptive status`)) lines.push(`Adaptive state: ${value(`${side} adaptive status`)}`);
    }
  }
  return lines;
}

export function stimulationAxisSettings(condition,participant) {
  const lines=stimulationSettingLines(condition,participant);
  return (lines.length?lines:['Settings not available']).map(escapeText).join('<br>');
}

export function stimulationDetailRows(condition,participant) {
  return (condition.settings || []).map(row=>{
    const label=condition.mode==='open_loop'&&/threshold/i.test(row.label)?`Stored ${row.label} (not controlling stimulation)`:row.label;
    return displayTargetText(participant,`${label}: ${row.value}`);
  });
}

export function stimulationSummary(condition,participant) {
  return [`<b>${escapeText(condition.label)}</b>`,surveyCount(condition),stimulationAxisSettings(condition,participant)].join('<br>');
}

export function stimulationPlot(metric,open,closed,reference=null,currentReference=null,options={}) {
  const finalized=finalizedProgram(metric,reference),current=finalizedProgram(metric,currentReference,'closed_loop','Current CL');
  const closedStart=options.mode==='closed_loop'?0:finalized||current?5:4;
  const slots=[...(options.mode!=='closed_loop'?[
    ...open.map((condition,i)=>({condition,position:i,title:`OL ${i+1}`})),
    ...(finalized?[{condition:finalized,position:3,title:'Finalized OL'}]:[])]:[]),
    ...(options.mode!=='open_loop'?[
      ...closed.map((condition,i)=>({condition,position:i+closedStart,title:`CL ${i+1}`})),
      ...(current?[{condition:current,position:closedStart+3,title:'Current CL'}]:[])]:[])];
  const populated=slots.filter(slot=>finitePoints(slot.condition).length>0);
  const plot=conditionPlot(metric,populated.map(slot=>slot.condition));
  const positions=populated.map(slot=>slot.position);
  plot.traces=plot.traces.map((trace,i)=>{
    const moved={...trace,x:trace.x.map(value=>value+positions[Math.floor(i/2)]-Math.floor(i/2))};
    // Plotly box hover produces several quartile labels. Only survey dots own a
    // hover target, yielding one detailed settings tooltip under closest mode.
    if(trace.type==='box') {delete moved.hovertemplate;return {...moved,hoverinfo:'skip'};}
    return {...moved,hovertemplate:`<b>${escapeText(metric.label)}: %{customdata[1]:.1f}</b><br>%{customdata[0]} Pacific<br>${stimulationSummary(populated[Math.floor(i/2)].condition,options.participant)}<extra></extra>`};
  });
  plot.fitWidth=true;
  plot.programs=slots.map(({condition,title,position})=>({condition,title,position,countLabel:surveyCount(condition),settings:stimulationSettingLines(condition,options.participant)}));
  plot.layout.height=390;
  plot.layout.hovermode='closest';
  plot.layout.xaxis={...plot.layout.xaxis,range:[-0.65,options.mode?3.65:current?closedStart+3.65:closedStart+2.65],tickvals:slots.map(slot=>slot.position),tickfont:{size:13},tickangle:0,fixedrange:true,
    ticktext:slots.map(({title})=>`<b>${title.replace(' ','<br>')}</b>`)};
  plot.layout.margin={l:55,r:15,t:25,b:65};
  plot.layout.annotations=options.mode?[]:[{xref:'paper',yref:'paper',x:0.2,y:1.12,text:'<b>Open loop</b>',showarrow:false,font:{size:18}},
    {xref:'paper',yref:'paper',x:0.8,y:1.12,text:'<b>Closed loop</b>',showarrow:false,font:{size:18}}];
  plot.layout.shapes=plot.layout.shapes.map((shape,i)=>({...shape,x0:shape.x0+positions[i]-i,x1:shape.x1+positions[i]-i}));
  if(!options.mode) plot.layout.shapes.push({type:'line',xref:'x',yref:'paper',x0:closedStart-1,x1:closedStart-1,y0:0,y1:1,line:{color:'#ccd2df',width:1,dash:'dot'}});
  const baseline=metric.baseline?.points || [];
  const values=baseline.filter(point=>Number.isFinite(point.value)).map(point=>point.value).sort((a,b)=>a-b);
  if(values.length) {
    const quantile=q=>{const at=(values.length-1)*q,lower=Math.floor(at),upper=Math.ceil(at);return values[lower]+(values[upper]-values[lower])*(at-lower);};
    plot.offReference={count:values.length,p30:quantile(0.3),median:quantile(0.5),p70:quantile(0.7),countLabel:surveyCount({points:baseline})};
    for(const [key,dash,width] of [['p30','dot',1],['median','dash',2],['p70','dot',1]]) plot.layout.shapes.push({type:'line',xref:'paper',yref:'y',x0:0,x1:1,y0:plot.offReference[key],y1:plot.offReference[key],line:{color:key==='median'?'#2E7D32':'#C62828',dash,width}});
  }
  plot.layout.shapes=[...plot.layout.shapes.filter(shape=>shape.name!=='Condition median'),...plot.layout.shapes.filter(shape=>shape.name==='Condition median')];
  return plot;
}

export function orderedMedicationConditions(conditions) {
  return [...conditions].sort((a,b)=>(a.drug_class_order??999)-(b.drug_class_order??999)||a.drug_class.localeCompare(b.drug_class)||a.label.localeCompare(b.label));
}

const groupRows = ordered => {
  const groups=[],positions=[];
  ordered.forEach((condition,index)=>{
    if(!index||condition.drug_class!==ordered[index-1].drug_class) groups.push({label:condition.drug_class,start:index+(groups.length*0.7),end:0});
    positions.push(index+(groups.length-1)*0.7);groups[groups.length-1].end=positions[index];
  });
  return {groups,positions};
};
const classShapes = groups => groups.map((group,index)=>({type:'rect',xref:'paper',yref:'y',x0:0,x1:1,y0:group.start-0.45,y1:group.end+0.45,line:{width:0},fillcolor:index%2?'rgba(53,102,155,0.04)':'rgba(53,102,155,0.09)',layer:'below'}));
const classHeaders = groups => groups.map(group=>({xref:'paper',yref:'y',x:0.01,y:group.start-0.5,text:`<b>${(String(group.label).match(/.{1,32}(?:\s|$)|.{1,32}/g)||['']).map(part=>escapeText(part.trim())).join('<br>')}</b>`,xanchor:'left',yanchor:'bottom',showarrow:false,font:{size:15,color:'#344767'}}));

export function medicationConditionPlot(metric,conditions) {
  const ordered=orderedMedicationConditions(conditions),plot=conditionPlot(metric,ordered,true),{groups,positions}=groupRows(ordered);
  plot.traces=plot.traces.map((trace,index)=>({...trace,y:trace.y.map(value=>value+positions[Math.floor(index/2)]-Math.floor(index/2))}));
  plot.layout.height=Math.max(350,conditions.length*55+groups.length*25+120);
  plot.layout.yaxis={...plot.layout.yaxis,tickvals:positions,range:[(positions.at(-1)??0)+0.6,-1],autorange:false};
  plot.layout.shapes=[...classShapes(groups),...plot.layout.shapes.map((shape,i)=>({...shape,y0:shape.y0+positions[i]-i,y1:shape.y1+positions[i]-i}))];
  plot.layout.annotations=classHeaders(groups);
  plot.rowLabels=ordered.map((condition,index)=>`${index+1}. ${condition.drug_class} · ${condition.label} · n=${condition.count} · median ${condition.median}`);
  plot.fitWidth=true;
  return plot;
}

export function medicationTimeline(episodes,throughDay,periodStart,phases=[]) {
  const ordered=[...episodes].sort((a,b)=>(a.drug_class_order??999)-(b.drug_class_order??999)||a.drug_class.localeCompare(b.drug_class)||a.name.localeCompare(b.name)||(a.start??0)-(b.start??0));
  const classes=[...new Set(ordered.map(episode=>episode.drug_class))];
  const {groups,positions}=groupRows(ordered);
  const endOfView=`${throughDay} 23:59:59`;
  const traces=ordered.flatMap((episode,index)=>{
    const knownStart=Number.isFinite(episode.start),knownEnd=Number.isFinite(episode.end);
    if(!knownStart&&!knownEnd&&!episode.ongoing) return [];
    const start=knownStart?Math.max(episode.start,periodStart??episode.start):null;
    const end=knownEnd?(localTime(episode.end)<=endOfView?localTime(episode.end):endOfView):null;
    const startText=knownStart?localTime(start):null;
    if((knownEnd&&Number.isFinite(periodStart)&&episode.end<periodStart)||(knownStart&&startText>endOfView)) return [];
    const complete=knownStart&&(knownEnd||episode.ongoing);
    const x=complete?[startText,end||endOfView]:[startText||end||(Number.isFinite(periodStart)?localTime(periodStart):endOfView)];
    const details=[episode.drug_class,episode.dose,episode.frequency,episode.route,episode.timing,episode.note].filter(Boolean).map(escapeText).join('<br>');
    const availability=episode.prn?'PRN available; use is not confirmed':'Documented regimen; use is not confirmed';
    const startLabel=knownStart?`From ${localTime(episode.start)} Pacific`:'Start date not recorded; endpoint marker only';
    const endLabel=knownEnd?`Through ${localTime(episode.end)} Pacific`:episode.ongoing?'Documented as ongoing; shown through current day':'End date not recorded; start marker only';
    const symbols=complete?[episode.pre_trial||start!==episode.start?'triangle-left':'circle',episode.ongoing?'triangle-right':'circle']:['diamond-open'];
    return [{type:'scatter',mode:complete?'lines+markers':'markers',x,y:x.map(()=>positions[index]),showlegend:false,
      line:{width:episode.supportive?5:10,color:PALETTE[classes.indexOf(episode.drug_class)%PALETTE.length],dash:episode.prn?'dot':'solid'},
      marker:{size:10,symbol:symbols},opacity:episode.supportive?0.6:1,
      hovertemplate:`<b>${escapeText(episode.name)}</b><br>${details}<br>${availability}<br>${startLabel}<br>${endLabel}<extra></extra>`}];
  });
  const boundaries=phases.filter(phase=>Number.isFinite(periodStart)&&phase.start>=periodStart&&localTime(phase.start)<=endOfView);
  let headerHeight=0;
  const boundaryHeaders=boundaries.map(phase=>{
    const lines=String(phase.label).match(/.{1,28}(?:\s|$)|.{1,28}/g)||[''];
    const annotation={x:localTime(phase.start),xref:'x',y:1,yref:'paper',yshift:14+headerHeight,
      yanchor:'bottom',text:lines.map(line=>escapeText(line.trim())).join('<br>'),showarrow:false,font:{size:14}};
    headerHeight+=lines.length*18+8;
    return annotation;
  });
  const topMargin=Math.max(45,headerHeight+20);
  return {traces,fitWidth:true,rowLabels:ordered.map((episode,index)=>`${index+1}. ${episode.drug_class} · ${[episode.name,episode.dose,episode.frequency].filter(Boolean).join(' · ')}`),layout:{height:Math.max(350,ordered.length*55+groups.length*25+110)+topMargin-45,margin:{l:250,r:35,t:topMargin,b:75},
    xaxis:{type:'date',title:{text:'Date · Pacific time',font:{size:17}},nticks:7,automargin:true,...(Number.isFinite(periodStart)?{range:[localTime(periodStart),endOfView]}:{})},
    yaxis:{tickmode:'array',tickvals:positions,ticktext:ordered.map(episode=>compactLabel([episode.name,episode.dose,episode.frequency].filter(Boolean).join(' · '))),range:[(positions.at(-1)??0)+0.6,-1],autorange:false,automargin:true},
    shapes:[...trialPhaseBands(phases,{start:Number.isFinite(periodStart)?localTime(periodStart).slice(0,10):traces.flatMap(t=>t.x).sort()[0]?.slice(0,10),end:throughDay}),...classShapes(groups),...boundaries.map(phase=>({type:'line',xref:'x',yref:'paper',x0:localTime(phase.start),x1:localTime(phase.start),y0:0,y1:1,line:{color:phase.color,dash:'dash',width:1}}))],
    annotations:[...classHeaders(groups),...boundaryHeaders]}};
}
