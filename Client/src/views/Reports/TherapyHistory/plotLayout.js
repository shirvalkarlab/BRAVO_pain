export const groupLabel = value => String(value).replace(/^GroupIdDef\.GROUP_([A-D])$/,'Group $1');

export function therapyLayout(width,height) {
  const compact=width>0&&width<600;
  return {autosize:true,height:Math.max(height||400,compact?420:350),margin:{l:compact?75:90,r:18,t:75,b:95},
    title:{font:{size:compact?16:20}},
    xaxis:{nticks:compact?4:7,automargin:true,tickfont:{size:12},tickformat:'%b %d<br>%Y'},
    yaxis:{automargin:true,tickfont:{size:12}},
  };
}
export function impedanceLayout(width,height) {
  const stacked=width>0&&width<700;
  return {rows:stacked?2:1,columns:stacked?1:2,
    layout:{autosize:true,height:Math.max(height||420,stacked?740:420),margin:{l:50,r:20,t:75,b:55}},
    spacing:{sharex:false,sharey:false,colSpacing:0.16,rowSpacing:0.35},
    ticks:{automargin:true,tickfont:{size:12},tickangle:0},
  };
}
