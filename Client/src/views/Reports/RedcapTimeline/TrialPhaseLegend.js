import {trialPhasesInRange} from './trialPhases';

export default function TrialPhaseLegend({phases, range}) {
  const visible = trialPhasesInRange(phases, range);
  if (!visible.length) return null;
  return <div aria-label="Trial phases in this chart" style={{margin:'12px 8px 8px', color:'#344767', fontSize:13, minWidth:0}}>
    <div style={{fontWeight:600, marginBottom:6}}>Trial phases · shaded sections</div>
    <ul style={{display:'flex', flexWrap:'wrap', gap:'6px 16px', listStyle:'none', padding:0, margin:0}}>
      {visible.map(phase => <li key={phase.key} tabIndex={0} title={phase.details}
        style={{display:'flex', alignItems:'flex-start', gap:6, minWidth:0, maxWidth:'100%', overflowWrap:'anywhere'}}>
        <span aria-hidden="true" style={{width:10,height:10,marginTop:4,flexShrink:0,background:phase.color,borderRadius:2}} />
        <span><strong>{phase.label}</strong><span style={{display:'block',fontSize:12}}>Shown: {phase.fromDay} – {phase.throughDay}</span></span>
      </li>)}
    </ul>
  </div>;
}
