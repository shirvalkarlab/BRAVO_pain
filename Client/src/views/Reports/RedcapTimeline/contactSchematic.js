import {escapeText} from './data';

// SenSight: distal ring, two levels of three segments, proximal ring.
// API contact numbers already use the right-lead offset; never remap them.
export function parseContactSet(source, side) {
  const raw=String(source ?? '').trim(), base=side==='right'?8:0;
  const polarities={},tokens=raw.replace(/Case/gi,'C').replace(/[−–]/g,'-').match(/(?:C|\d+[abc]?)\s*[+-]/gi)||[];
  const remainder=raw.replace(/Case/gi,'C').replace(/[−–]/g,'-').replace(/(?:C|\d+[abc]?)\s*[+-]/gi,'').replace(/[\s,;]/g,'');
  let valid=tokens.length>0&&!remainder;
  for(const token of tokens){
    const match=token.match(/^(C|\d+[abc]?)\s*([+-])$/i),id=match[1].toUpperCase()==='C'?'C':match[1].toLowerCase(),polarity=match[2];
    const level=Number.parseInt(id,10),segment=/[abc]$/.test(id);
    if(id!=='C'&&(!/^(?:0|[1-9]\d*)[abc]?$/.test(id)||![base,base+1,base+2,base+3].includes(level)||(segment&&![base+1,base+2].includes(level))))valid=false;
    const ids=id!=='C'&&!segment&&[base+1,base+2].includes(level)?['a','b','c'].map(s=>`${level}${s}`):[id];
    for(const key of ids){if(polarities[key]&&polarities[key]!==polarity)valid=false;polarities[key]=polarity;}
  }
  return {raw,valid,base,polarities:valid?polarities:{}};
}
export function contactConfiguration(programs, knownGeometry) {
  const leads=programs.map(program=>({...program,contacts:parseContactSet(program.rows['Stimulation contacts'],program.side)})).sort((a,b)=>a.id.localeCompare(b.id));
  const key=JSON.stringify(leads.map(p=>[p.id,p.contacts.valid?Object.entries(p.contacts.polarities).sort():p.contacts.raw]));
  return {key,leads,knownGeometry};
}
const fill = polarity=>polarity==='-'?'#246EA0':polarity==='+'?'#B3456A':'#E7EBEF';
function leadSvg(program,x,knownGeometry){
  const {contacts}=program, {base,polarities}=contacts;
  const side=program.side==='left'?'L':'R',programNumber=program.id.split(':')[1];
  let svg=`<text x="${x+37}" y="12" text-anchor="middle" font-size="11" font-weight="600">${side}${programNumber?` · P${escapeText(programNumber)}`:''}</text>`;
  if(!knownGeometry||!contacts.valid){return svg+`<rect x="${x+3}" y="20" width="68" height="91" rx="9" fill="#F3F5F7" stroke="#CBD5DF" stroke-dasharray="3 3"/><text x="${x+37}" y="55" text-anchor="middle" font-size="10">${knownGeometry?'Contacts':'Geometry'}</text><text x="${x+37}" y="69" text-anchor="middle" font-size="10">unresolved</text>`;}
  const contact=(id,cx,cy,width)=>{
    const polarity=polarities[id];return `<rect x="${cx}" y="${cy}" width="${width}" height="16" rx="3" fill="${fill(polarity)}" stroke="#A7B4C2" stroke-width="0.6"/><text x="${cx+width/2}" y="${cy+11}" text-anchor="middle" font-size="9" fill="${polarity?'white':'#536477'}">${id}${polarity==='-'?'−':polarity||''}</text>`;
  };
  svg+=contact('C',x+16,19,42);
  svg+=`<path d="M${x+37} 36V41" stroke="#A7B4C2"/><rect x="${x+3}" y="40" width="68" height="87" rx="12" fill="#F5F7F9" stroke="#A7B4C2"/>`;
  for(let level=3;level>=0;level--){const y=45+(3-level)*20;if(level===0||level===3)svg+=contact(String(base+level),x+7,y,60);else for(let i=0;i<3;i++)svg+=contact(`${base+level}${'abc'[i]}`,x+7+i*20,y,19);}
  return svg;
}
export function configurationSvg(configuration,number) {
  const width=26+Math.max(configuration.leads.length,1)*80;
  const drawings=configuration.leads.map((p,i)=>leadSvg(p,26+i*80,configuration.knownGeometry)).join('');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} 132"><g font-family="Arial, sans-serif" fill="#344767"><text x="2" y="74" font-size="11" font-weight="600">C${number}</text>${drawings||'<text x="38" y="65" font-size="11">Contacts not recorded</text>'}</g></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
