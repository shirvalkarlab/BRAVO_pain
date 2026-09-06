export function chartLayout(width, traces, height, xTitle, yTitle) {
  const compact = width > 0 && width < 600;
  const legends = traces.filter(trace => trace.showlegend !== false).length;
  const showlegend = traces.length > 1;
  const legendSpace = showlegend ? (compact ? Math.max(70, legends * 22 + 25) : 90) : 55;
  return {
    autosize:true, height:Math.max(height, 215 + legendSpace),
    margin:{l:compact ? 55 : 65,r:compact ? 14 : 30,t:15,b:legendSpace},
    paper_bgcolor:'transparent',plot_bgcolor:'transparent',
    font:{family:'Roboto, sans-serif',color:'#344767',size:14},
    xaxis:{title:xTitle,automargin:true,nticks:compact ? 4 : 6},
    yaxis:{title:yTitle,automargin:true,zeroline:false,nticks:compact ? 5 : 7},
    showlegend,legend:{orientation:compact ? 'v' : 'h',x:0,xanchor:'left',y:-0.28,yanchor:'top',font:{size:12}},
  };
}
