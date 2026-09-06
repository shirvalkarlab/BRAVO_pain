import {useEffect,useMemo,useRef,useState} from 'react';
import Plotly from 'plotly.js-dist';
import {HOME_NEURAL_COLORS,homeNeuralLayout,homeNeuralPlot,neuralSourceLabel} from './homeNeuralChartData';
import {localTime} from './data';

// This visible source key is shared with the multimodal summary. It identifies
// every interval separately, including repeated configurations on different days.
export function NeuralSensingIntervals({descriptions,onSegment}) {
  if (!descriptions.length) return null;
  const stamp=time=>localTime(time).slice(0,16);
  return <section aria-label="Recorded sensing intervals" style={{fontSize:14,margin:'8px',lineHeight:1.6,minWidth:0}}>
    <div style={{fontWeight:600,marginBottom:8}}>Recorded sensing intervals · {descriptions.length}</div>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,260px),1fr))',gap:10}}>
      {descriptions.map((description,index)=><div key={`${description.id}:${index}`} data-sensing-interval={description.id}
        style={{padding:'10px 12px',border:'1px solid #dce5ef',borderRadius:8,minWidth:0,overflowWrap:'anywhere',background:'#f7f9fc'}}>
        <div style={{color:'#526179',fontSize:12}}>{stamp(description.start)} → {stamp(description.end)} Pacific</div>
        <div style={{fontWeight:600,color:HOME_NEURAL_COLORS.power}}>Sensing: {description.source} · contacts {description.contacts}</div>
        <div style={{fontWeight:600}}>{description.center}</div>
        {description.band !== description.center&&<div>{description.band}</div>}
        <div>{description.mode}</div>
        <div>Control mapping: {description.mappingStatus || 'Not established'}</div>
        {description.thresholdStatus&&<div>{description.thresholdStatus}</div>}
        {onSegment&&<button type="button" onClick={()=>onSegment(description.id)}
          aria-label={`Complete settings for ${description.source}, ${stamp(description.start)}`}
          style={{border:0,background:'none',color:HOME_NEURAL_COLORS.power,padding:'4px 0 0',font:'inherit',textAlign:'left',cursor:'pointer',textDecoration:'underline'}}>
          Complete settings
        </button>}
      </div>)}
    </div>
  </section>;
}

export function NeuralLegend({target,traces}) {
  return <div aria-label={`${target} chart legend`} style={{display:'flex',flexWrap:'wrap',gap:'5px 20px',fontSize:14,margin:'4px 8px 8px',lineHeight:1.7}}>
      <span style={{color:HOME_NEURAL_COLORS.power}}>● Biomarker · left axis</span>
      <span style={{color:HOME_NEURAL_COLORS.amplitude}}>● {target} amplitude · right axis</span>
      {traces.some(trace=>trace.line.dash)&&<span style={{color:HOME_NEURAL_COLORS.threshold}}>┄ Configured threshold(s)</span>}
    </div>;
}

export default function HomeNeuralChart({panel,window:period,participant,onSegment}) {
  const ref=useRef(null),[width,setWidth]=useState(0);
  const plot=useMemo(()=>homeNeuralPlot(panel,period,participant),[panel,period,participant]);
  const target=neuralSourceLabel(panel.side,participant);
  useEffect(()=>{const element=ref.current;return()=>Plotly.purge(element);},[]);
  useEffect(()=>{
    const element=ref.current;
    Plotly.react(element,plot.traces,homeNeuralLayout(period,width),{responsive:true,displaylogo:false,scrollZoom:false,
      modeBarButtonsToRemove:['lasso2d','select2d']});
    const select=event=>{
      const id=event.points?.[0]?.customdata?.[0];
      if(id !== undefined && id !== null) onSegment?.(id);
    };
    if(element.on) element.on('plotly_click',select);
    return()=>{if(element.removeListener) element.removeListener('plotly_click',select);};
  },[plot,period,width,onSegment]);
  useEffect(()=>{
    if(typeof ResizeObserver==='undefined') return;
    const element=ref.current;let frame;
    const observer=new ResizeObserver(()=>{
      cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>setWidth(element.clientWidth));
    });
    setWidth(element.clientWidth);observer.observe(element);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  return <div style={{minWidth:0}}>
    <NeuralLegend target={target} traces={plot.traces}/>
    <div ref={ref} role="img" aria-label={`${target} home biomarker and stimulation amplitude, ${period.label}`} style={{width:'100%',minWidth:0,minHeight:360}}/>
    <NeuralSensingIntervals descriptions={plot.descriptions} onSegment={onSegment}/>
    <p style={{fontSize:13,margin:'8px',color:'#526179',lineHeight:1.7}}>
      Recorded averages: {plot.observedPower.toLocaleString()} biomarker · {plot.observedAmplitude.toLocaleString()} amplitude.
      {plot.latestTime !== null&&<> Latest recorded average: {localTime(plot.latestTime).slice(0,16)} Pacific.</>}
      {' '}Points are recorded averages; connecting lines are guides. Gaps over 20 minutes stay open.
    </p>
    {(!plot.observedPower || !plot.observedAmplitude)&&<p style={{fontSize:14,margin:'8px',color:'#526179'}}>
      {!plot.observedPower&&'No established biomarker samples in this window. '}
      {!plot.observedAmplitude&&'No established stimulation-amplitude samples in this window.'}
    </p>}
  </div>;
}
