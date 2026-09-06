import { memo, useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist";
import {chartLayout} from './chartLayout';

export default memo(function Chart({traces, yTitle, xTitle = "Oura day", height = 290}) {
  const ref = useRef(null);
  const [width,setWidth] = useState(0);
  const layout = chartLayout(width,traces,height,xTitle,yTitle);
  useEffect(() => {
    const element = ref.current;
    return () => Plotly.purge(element);
  }, []);
  useEffect(() => {
    Plotly.react(ref.current, traces, chartLayout(width,traces,height,xTitle,yTitle), {responsive: true, displaylogo: false});
  }, [traces, yTitle, xTitle, height,width]);
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const element = ref.current;
    let frame;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { setWidth(element.getBoundingClientRect().width); if (element._fullLayout) Plotly.Plots.resize(element); });
    });
    observer.observe(element);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  return <div style={{width: "100%", minWidth: 0}}><div ref={ref} role="img" aria-label={yTitle} style={{width: "100%", minWidth: 0, minHeight: layout.height}} /></div>;
});
