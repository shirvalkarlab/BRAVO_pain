import {useEffect, useMemo, useRef, useState} from 'react';
import Plotly from 'plotly.js-dist';
import {hoverTime, relayoutRange, summaryLayout} from './multimodalData';

export default function MultimodalChart({title, traces, range, xRange, onRange, events, onTransition, left, right, limits, cursor, onCursor, neuralPeriod, onPoint}) {
  const ref = useRef(null), [width, setWidth] = useState(0);
  const layout = useMemo(() => summaryLayout({range, xRange, width, left, right, limits, events, neuralPeriod}), [range,xRange,width,left,right,limits,events,neuralPeriod]);
  useEffect(() => {const element = ref.current; return () => Plotly.purge(element);}, []);
  useEffect(() => {
    const element = ref.current;
    Plotly.react(element, traces, layout, {responsive: true, displaylogo: false, scrollZoom: false, modeBarButtonsToRemove: ['select2d','lasso2d']});
    const zoom = event => {const next = relayoutRange(event); if (next !== undefined) onRange(next);};
    const select = event => onTransition(event.annotation.name);
    const hover = event => {if (event.points?.length) onCursor(hoverTime(event.points[0].x));};
    const point = event => {const id = event.points?.[0]?.customdata?.[0]; if (id !== undefined && id !== null) onPoint?.(id);};
    const unhover = () => onCursor(null);
    const handlers = {plotly_relayout:zoom, plotly_clickannotation:select, plotly_hover:hover, plotly_unhover:unhover, plotly_click:point};
    Object.entries(handlers).forEach(([name, fn]) => element.on?.(name, fn));
    return () => Object.entries(handlers).forEach(([name, fn]) => element.removeListener?.(name, fn));
  }, [traces,layout,onRange,onTransition,onCursor,onPoint]);
  useEffect(() => {
    if (ref.current._fullLayout) Plotly.relayout(ref.current, {shapes: [...layout.shapes, ...(cursor ? [{type:'line',xref:'x',yref:'paper',x0:cursor,x1:cursor,y0:0,y1:1,line:{color:'#768299',width:1,dash:'dot'},layer:'above'}] : [])]});
  }, [cursor,layout]);
  useEffect(() => {
    const element = ref.current; let frame;
    if (typeof ResizeObserver === 'undefined') return;
    const measure = () => setWidth(element.clientWidth);
    measure();
    const observer = new ResizeObserver(() => {cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);});
    observer.observe(element);
    return () => {observer.disconnect();cancelAnimationFrame(frame);};
  }, []);
  return <div ref={ref} role="img" aria-label={title} data-summary-chart style={{width:'100%',minWidth:0,minHeight:370}}/>;
}
