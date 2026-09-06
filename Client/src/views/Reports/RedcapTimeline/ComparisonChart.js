import {useEffect,useRef,useState} from 'react';
import Plotly from 'plotly.js-dist';
import {escapeText} from './data';

export default function ComparisonChart({plot,label}) {
  const ref=useRef(null),container=useRef(null);
  const [width,setWidth]=useState(0);
  const narrow=width>0&&width<700;
  const [visible,setVisible]=useState(()=>typeof IntersectionObserver==='undefined');
  useEffect(()=>{
    if(typeof IntersectionObserver==='undefined') return;
    let active=true;
    const observer=new IntersectionObserver(entries=>{
      if(active&&entries.some(entry=>entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    },{rootMargin:'400px'});
    observer.observe(container.current);
    return()=>{active=false;observer.disconnect();};
  },[]);
  useEffect(()=>{if(!visible) return;const node=ref.current;return()=>Plotly.purge(node);},[visible]);
  useEffect(()=>{
    if(!visible) return;
    const layout={...plot.layout};
    if(plot.rowLabels?.length) {
      const labels=plot.rowLabels.map(label=>(label.match(/.{1,25}(?:\s|$)|.{1,25}/g)||['']).map(part=>escapeText(part.trim())).join('<br>'));
      const rowHeight=Math.max(55,...labels.map(label=>label.split('<br>').length*16+12));
      layout.height=narrow?plot.layout.height:Math.max(plot.layout.height,plot.rowLabels.length*rowHeight+180);
      layout.margin={...plot.layout.margin,l:narrow?40:230,r:20};
      layout.yaxis={...plot.layout.yaxis,ticktext:narrow?plot.rowLabels.map((_,i)=>String(i+1)):labels,tickfont:{size:narrow?13:12}};
      layout.xaxis={...plot.layout.xaxis,nticks:narrow?4:7};
      // Class names remain complete in the local regimen key; phase names also
      // remain in the chart-local trial legend when mobile header space is tight.
      if(narrow) layout.annotations=[];
    }
    Plotly.react(ref.current,plot.traces,{paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Roboto, sans-serif',size:16,color:'#344767'},
      hoverlabel:{font:{size:15}},showlegend:false,...layout},{responsive:true,displaylogo:false,scrollZoom:false,modeBarButtonsToRemove:['lasso2d','select2d']});
  },[plot,visible,width]);
  useEffect(()=>{
    if(!visible||typeof ResizeObserver==='undefined') return;
    const node=ref.current;let frame;
    const measure=()=>setWidth(node.getBoundingClientRect().width);
    measure();
    const observer=new ResizeObserver(()=>{
      cancelAnimationFrame(frame);
      frame=requestAnimationFrame(()=>{measure();if(node._fullLayout) Plotly.Plots.resize(node);});
    });
    observer.observe(node);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[visible]);
  return <div ref={container} style={{width:'100%',minWidth:0,overflowX:'visible',minHeight:plot.layout.height||350}}>
    {visible?<div ref={ref} role="img" aria-label={label} style={{minWidth:0,width:'100%',maxWidth:'100%'}}/>
      :<div role="status" aria-label={`${label} loading when visible`} style={{padding:'24px 16px',color:'#526179',fontSize:16}}>Scroll to view this interactive chart.</div>}
    {visible&&plot.rowLabels?.length>0&&<div aria-label={`${label} complete row labels`} style={{marginTop:12,fontSize:14,color:'#344767',overflowWrap:'anywhere'}}>
      <strong>Regimen key{narrow?' · numbers match chart rows':''}</strong>
      <ul style={{listStyle:'none',padding:0,display:'grid',gap:8}}>{plot.rowLabels.map((text,i)=><li key={i}>{text}</li>)}</ul>
    </div>}
  </div>;
}
