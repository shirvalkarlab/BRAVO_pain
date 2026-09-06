import {Alert,Box,Card,Stack} from '@mui/material';
import MDTypography from 'components/MDTypography';
import ComparisonChart from './ComparisonChart';
import {comparisonCoverage,finalizedProgram,stimulationPlot,stimulationDetailRows,topPrograms} from './comparisonData';

export default function StimulationPrograms({comparison,metrics,participant}) {
  if(!comparison?.available) return <Alert severity="info">{comparison?.message || 'Stimulation-program comparisons are not available for this participant.'}</Alert>;
  const reference=comparison.finalized_open_loop,currentReference=comparison.current_closed_loop;
  return <Stack spacing={3}>
    <Alert severity="info">Stage 1 onward · Up to three open-loop and three closed-loop programs per metric, each with at least five nonmissing surveys, ordered by lowest observed median. These are descriptive comparisons; differences do not establish a treatment effect.</Alert>
    {reference?.available&&<MDTypography variant="body2">Finalized OL is always shown in the fourth open-loop position, including when it is also among the top three or has fewer than five surveys. Reference: {reference.source?.url?<a href={reference.source.url} target="_blank" rel="noreferrer">{reference.source.title}</a>:'reviewed home-program settings'}{reference.source?.range?` · ${reference.source.range}`:''}.</MDTypography>}
    {currentReference?.available&&<MDTypography variant="body2">Current CL is always shown in the fourth closed-loop position, including when it has fewer than five surveys. Reference: {currentReference.source?.url?<a href={currentReference.source.url} target="_blank" rel="noreferrer">{currentReference.source.title}</a>:'reviewed current home-program settings'}{currentReference.source?.range?` · ${currentReference.source.range}`:''}.</MDTypography>}
    <MDTypography variant="body2">{comparisonCoverage(comparison.provenance)}</MDTypography>
    {!metrics.length && <Alert severity="info">Select a clinical metric above to compare its stimulation programs.</Alert>}
    {metrics.map(selected=>{
      const metric=comparison.metrics.find(item=>item.key===selected.key);
      const open=metric?topPrograms(metric,'open_loop'):[],closed=metric?topPrograms(metric,'closed_loop'):[];
      const finalized=metric?finalizedProgram(metric,reference):null;
      const current=metric?finalizedProgram(metric,currentReference,'closed_loop','Current CL'):null;
      const plots=metric?['open_loop','closed_loop'].map(mode=>({mode,label:mode==='open_loop'?'Open loop':'Closed loop',plot:stimulationPlot(metric,open,closed,reference,currentReference,{mode,participant})})).filter(item=>item.plot.programs.length):[];
      const offReference=plots[0]?.plot.offReference;
      return <Card key={selected.key} sx={{p:{xs:1.5,sm:3},minWidth:0}}><MDTypography variant="h4">{selected.label}</MDTypography>
        {!metric?<Alert severity="info">No eligible comparison data for this metric.</Alert>:<>
          {!open.length&&<Alert severity="info" sx={{mt:2}}>No open loop program has five eligible surveys for this metric.</Alert>}
          {!closed.length&&<Alert severity="info" sx={{mt:2}}>No closed loop program has five eligible surveys for this metric.</Alert>}
          {(open.length+closed.length>0||finalized||current)&&<>
            {plots.map(({mode,label,plot})=><Box key={mode} sx={{mt:3,minWidth:0}}>
              <MDTypography variant="h5">{label}</MDTypography>
              <ComparisonChart plot={plot} label={`${selected.label} ${label.toLowerCase()} program comparison`}/>
              <Box sx={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(min(100%, 240px), 1fr))',gap:2,minWidth:0}}>
                {plot.programs.map(({condition,title,countLabel,settings},index)=><Box component="section" aria-label={`${title} settings`} key={`${condition.id}-${index}`} sx={{p:2,border:'1px solid #e1e6ef',borderRadius:2,minWidth:0,overflowWrap:'anywhere'}}>
                  <MDTypography variant="h6">{title}</MDTypography>
                  <MDTypography variant="body2">{countLabel}</MDTypography>
                  <MDTypography variant="body2">{condition.count?`Median ${condition.median}`:'No eligible surveys'}</MDTypography>
                  <Box sx={{mt:1}}>{(settings.length?settings:['Settings not available']).map((line,i)=><MDTypography component="div" variant="body2" key={i}>{line}</MDTypography>)}</Box>
                  <details style={{marginTop:12}}><summary>All recorded settings</summary><ul style={{paddingLeft:20}}>{stimulationDetailRows(condition,participant).map((line,i)=><li key={i}>{line}</li>)}</ul></details>
                </Box>)}
              </Box>
            </Box>)}
            <MDTypography variant="body2">Solid dark lines mark each program’s median; boxes span the middle 50% of survey scores. Hover over a survey point for settings and its score. Days count distinct Pacific survey dates.</MDTypography>
            {offReference&&<MDTypography variant="body2">Stimulation OFF reference ({offReference.countLabel}): green dashed line = median {offReference.median.toFixed(1)}; red dotted lines = 30th–70th percentiles ({offReference.p30.toFixed(1)}–{offReference.p70.toFixed(1)}).</MDTypography>}
          </>}
        </>}
      </Card>;
    })}
  </Stack>;
}
