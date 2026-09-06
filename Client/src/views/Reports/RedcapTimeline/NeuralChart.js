import {useEffect,useMemo,useRef,useState} from 'react';
import Plotly from 'plotly.js-dist';
import {escapeText,transitionLayout} from './data';
import {trialPhaseBands} from './trialPhases';
import TrialPhaseLegend from './TrialPhaseLegend';
import {neuralPlot} from './neuralTimelineData';
import {configurationSvg} from './contactSchematic';
import {displayTarget} from 'utils/participantTargets';

const wrap = text => text.match(/.{1,25}(?:\s|$)|.{1,25}/g).map(line=>escapeText(line.trim())).join('<br>');
export default function NeuralChart({metric,events,range,participant,phases,unknownIntervals,transitions,onSelect}) {
  const ref=useRef(null),[width,setWidth]=useState(0);
  const contacts=metric.key==='contacts',compact=width>0&&width<600;
  const plot=useMemo(()=>neuralPlot(events,metric,range,participant,unknownIntervals),[events,metric,range,participant,unknownIntervals]);
  useEffect(()=>{const node=ref.current;return()=>Plotly.purge(node);},[]);
  useEffect(()=>{
    const node=ref.current,context=transitionLayout(transitions);
    const left=contacts?(compact?45:224):metric.categorical?190:65;
    const plotWidth=Math.max(60,(width||node.clientWidth)-left-20);
    const images=contacts&&!compact?plot.configurations.map((configuration,i)=>({source:configurationSvg(configuration,configuration.number),xref:'paper',yref:'y',x:-8/plotWidth,y:i,sizex:190/plotWidth,sizey:0.88,xanchor:'right',yanchor:'middle',sizing:'contain',layer:'above'})):[];
    const midpoint=(Date.parse(`${range.start}T00:00:00Z`)+Date.parse(`${range.end}T23:59:59Z`))/2;
    context.annotations=context.annotations.map(annotation=>({...annotation,xanchor:Date.parse(annotation.x.replace(' ','T')+'Z')>midpoint?'right':'left'}));
    Plotly.react(node,plot.traces,{
      autosize:true,height:Math.max(430,metric.categorical?plot.categories.length*(contacts&&!compact?138:65)+180:0)+(transitions.length?65:0),
      margin:{l:left,r:20,t:transitions.length?110:20,b:110},
      paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Roboto, sans-serif',color:'#344767',size:14},
      xaxis:{type:'date',range:[`${range.start} 00:00:00`,`${range.end} 23:59:59`],title:'Date · Pacific time',nticks:6,automargin:true},
      yaxis:metric.categorical?{showticklabels:!contacts||compact,tickmode:'array',tickvals:plot.categories.map((_,i)=>i),ticktext:plot.categories.map(wrap),range:contacts?[Math.max(plot.categories.length-0.4,0.6),-0.6]:[-0.6,Math.max(plot.categories.length-0.4,0.6)],automargin:true,zeroline:false}:{title:metric.unit,automargin:true,zeroline:false,rangemode:'tozero'},
      images,shapes:[...trialPhaseBands(phases,range),...plot.shapes,...context.shapes],annotations:context.annotations,
      hovermode:'closest',showlegend:!metric.categorical,legend:{orientation:'h',x:0,y:-0.22,yanchor:'top'},
      uirevision:`${metric.key}:${range.start}:${range.end}`,
    },{responsive:true,displaylogo:false,scrollZoom:false,modeBarButtonsToRemove:['lasso2d','select2d']});
    const point=event=>{const id=event.points?.[0]?.customdata?.[0];if(id)onSelect(id);};
    const annotation=event=>onSelect(event.annotation.name);
    if(node.on){node.on('plotly_click',point);node.on('plotly_clickannotation',annotation);}
    return()=>{if(node.removeListener){node.removeListener('plotly_click',point);node.removeListener('plotly_clickannotation',annotation);}};
  },[plot,metric,range,phases,transitions,onSelect,width,contacts,compact]);
  useEffect(()=>{
    if(typeof ResizeObserver==='undefined')return;
    const node=ref.current;let frame;
    const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>setWidth(node.clientWidth));});
    setWidth(node.clientWidth);
    observer.observe(node);return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  return <div style={{minWidth:0}}>
    {contacts&&<div style={{fontSize:14,margin:'12px 8px',lineHeight:1.7}}>
      <strong>Each row is a paired lead configuration.</strong> L = {displayTarget(participant,'left','left lead')}; R = {displayTarget(participant,'right','right lead')}. Changes connect as one configuration timeline.
      <div><span style={{color:'#246EA0',fontWeight:600}}>− Cathode</span> · <span style={{color:'#B3456A',fontWeight:600}}>+ Anode</span> · Gray = not selected · C = pulse-generator case.</div>
      <div>SenSight schematics are unwrapped, with the tip down; rotational anatomy is not shown. Color shows configured polarity, not measured current.</div>
    </div>}
    {metric.key==='mode'&&<p style={{fontSize:14,margin:'12px 8px',lineHeight:1.7}}>One device/group state. Read the categories from bottom to top: fixed without cycling, cycling ordered by increasing ON time then OFF time, and closed-loop single or dual threshold. Durations are in minutes. Unresolved source states are labeled separately.</p>}
    <TrialPhaseLegend phases={phases} range={range}/>
    <div ref={ref} role="img" aria-label={`${metric.label} neural settings timeline`} style={{width:'100%',minWidth:0,minHeight:430}}/>
    {contacts&&compact&&<div aria-label="Contact configuration schematics" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(170px,1fr))',gap:12,margin:'12px 8px'}}>
      {plot.configurations.map((configuration,i)=><figure key={configuration.key} style={{margin:0,padding:12,border:'1px solid #dce3eb',borderRadius:12,minWidth:0}}>
        <img src={configurationSvg(configuration,configuration.number)} alt={`C${configuration.number}: ${configuration.leads.map(p=>`${p.label} ${p.contacts.raw||'contacts not recorded'}`).join('; ')}`} style={{width:'100%',height:150,objectFit:'contain'}}/>
        <figcaption style={{fontSize:13,overflowWrap:'anywhere'}}>{configuration.leads.map(p=><div key={p.id}>{p.label}: {p.contacts.raw||'Contacts not recorded'}</div>)}</figcaption>
      </figure>)}
    </div>}
    {plot.unresolved.length>0&&<details style={{fontSize:14,margin:'8px',overflowWrap:'anywhere'}}><summary>{plot.unresolved.length} {plot.unresolved.length===1?'record':'records'} without an unambiguous numeric value</summary>
      <ul>{plot.unresolved.map((record,i)=><li key={`${record.id}:${i}`}><button onClick={()=>onSelect(record.id)} style={{cursor:'pointer',color:'#356E9B',background:'none',border:0,textAlign:'left',font:'inherit'}}>{record.time} · {record.target}: {record.raw}</button></li>)}</ul>
    </details>}
    {!plot.traces.length&&<p>No recorded values are established for this parameter in the selected window.</p>}
  </div>;
}
