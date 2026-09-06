import {currentTargetText} from 'utils/participantTargets';
const escape = text => String(text).replace(/[&<>]/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[character]));
export function snapshotLayout(width, bars, legendCount = 0) {
  const compact = width > 0 && width < 600;
  const legendSpace = bars ? 100 : compact ? Math.max(90,legendCount*20+35) : 110;
  return {
    autosize:true,height:Math.max(compact ? 400 : 460,270+legendSpace),
    margin:{l:compact ? 60 : 75,r:15,t:55,b:legendSpace},
    title:{font:{size:compact ? 16 : 18}},
    legend:{orientation:compact ? 'v' : 'h',x:0,xanchor:'left',y:-0.26,yanchor:'top',font:{size:12}},
  };
}
export function snapshotTicks(labels, width) {
  const unique = [...new Set(labels)], limit = Math.max(2,Math.floor((width || 800)/95));
  const stride = Math.max(1,Math.ceil(unique.length/limit));
  const ticks = unique.filter((_,index)=>index%stride===0 || index===unique.length-1);
  return {tickmode:'array',tickvals:ticks,ticktext:ticks.map(label=>escape(currentTargetText(label)).replace(/(.{10,18})\s/g,'$1<br>')),tickangle:-35,automargin:true,tickfont:{size:11}};
}
