import {useState} from 'react';
import {Alert,Box,Button,Card,Stack} from '@mui/material';
import MDTypography from 'components/MDTypography';
import ComparisonChart from './ComparisonChart';
import {finalizedProgram,stimulationPlot,stimulationDetailRows,topPrograms,programRankingLabel,programMetricCoverage,programSourceCoverage,reviewedReferenceTiming} from './comparisonData';

export default function StimulationPrograms({comparison,metrics,participant}) {
  const [selection,setSelection]=useState(null);
  if(!comparison?.available||comparison.provenance?.calendar_verified===false) return <Alert severity="info">{comparison?.message || (comparison?.provenance?.calendar_verified===false?'A verified stored testing calendar is required before program rankings can be shown.':'Stimulation-program comparisons are not available for this participant.')}</Alert>;
  const reference=comparison.finalized_open_loop,currentReference=comparison.current_closed_loop;
  const sourceMetric=comparison.metrics.find(metric=>metric.key===selection?.metricKey);
  const rankedSelection=sourceMetric?.conditions.find(condition=>condition.id===selection.id && condition.mode===selection.mode);
  const referenceSelection=selection?.reference && (selection.mode==='open_loop'?reference:currentReference);
  const chosen=rankedSelection || (referenceSelection?.available?referenceSelection:null);
  const title=referenceSelection?(selection.mode==='open_loop'?'Finalized OL':'Reviewed CL'):'Selected';
  return <Stack spacing={3}>
    <Alert severity="info">Stage 1 onward · Up to three open-loop and three closed-loop programs per metric, each with at least five eligible nonmissing surveys. Ranking follows the metric’s favorable direction: lower pain scores or higher relief scores. These are descriptive comparisons; differences do not establish a treatment effect.</Alert>
    <MDTypography variant="body2">Eligible surveys have a recorded finite value and valid time outside documented testing days and within the reviewed comparison period. Eligible surveys without a verified program are counted but do not enter program comparisons.</MDTypography>
    {comparison.message&&<MDTypography variant="body2">{comparison.message}</MDTypography>}
    {reference?.available&&<MDTypography variant="body2"><Button onClick={()=>setSelection({mode:'open_loop',reference:true})}>Compare finalized OL</Button> Reference: {reference.source?.url?<a href={reference.source.url} target="_blank" rel="noreferrer">{reference.source.title}</a>:'reviewed home-program settings'}{reference.source?.range?` · ${reference.source.range}`:''}. {reviewedReferenceTiming(reference)}</MDTypography>}
    {currentReference?.available&&<MDTypography variant="body2"><Button onClick={()=>setSelection({mode:'closed_loop',reference:true})}>Compare reviewed CL reference</Button> Reference: {currentReference.source?.url?<a href={currentReference.source.url} target="_blank" rel="noreferrer">{currentReference.source.title}</a>:'reviewed home-program settings'}{currentReference.source?.range?` · ${currentReference.source.range}`:''}. {reviewedReferenceTiming(currentReference)}</MDTypography>}
    <MDTypography variant="body2">Click a ranked box, a survey point, or its Compare button to show that setting in the fourth position for the other metrics in the same loop mode.</MDTypography>
    {chosen&&<Box role="status"><MDTypography variant="body2">Comparing {rankedSelection?chosen.label:title}{sourceMetric?` from ${sourceMetric.label}`:''} across metrics.</MDTypography><Button onClick={()=>setSelection(null)}>Clear comparison</Button></Box>}
    <Stack spacing={1} sx={{minWidth:0,overflowWrap:'anywhere'}} aria-label="Program comparison source coverage">{programSourceCoverage(comparison.provenance).map((line,index)=><MDTypography key={index} variant="body2">{line}</MDTypography>)}</Stack>
    {!metrics.length && <Alert severity="info">Select a clinical metric above to compare its stimulation programs.</Alert>}
    {metrics.map(selected=>{
      const metric=comparison.metrics.find(item=>item.key===selected.key);
      const open=metric?topPrograms(metric,'open_loop'):[],closed=metric?topPrograms(metric,'closed_loop'):[];
      const plots=metric?['open_loop','closed_loop'].map(mode=>{
        const compare=chosen && chosen.mode===mode && metric.key!==selection.metricKey;
        const comparisonProgram=compare?finalizedProgram(metric,{...chosen,available:true},mode,chosen.label || title):null;
        const plot=stimulationPlot(metric,open,closed,null,null,{mode,participant,comparisonProgram,comparisonTitle:title});
        const select=id=>setSelection({metricKey:metric.key,mode,id});
        return {mode,label:mode==='open_loop'?'Open loop':'Closed loop',plot,select};
      }).filter(item=>item.plot.programs.length):[];
      const offReference=plots[0]?.plot.offReference;
      return <Card key={selected.key} sx={{p:{xs:1.5,sm:3},minWidth:0}}><MDTypography variant="h4">{selected.label}</MDTypography>
        {!metric?<Alert severity="info">No eligible comparison data for this metric.</Alert>:<>
          <MDTypography variant="body2">{programRankingLabel(metric)}. Equal medians retain the source ranking order.</MDTypography>
          <Box component="section" aria-label={`${selected.label} eligibility and exclusions`} sx={{mt:1,mb:2,minWidth:0,overflowWrap:'anywhere'}}>
            <ul style={{margin:0,paddingLeft:20,fontSize:14}}>{programMetricCoverage(metric).map((line,index)=><li key={index}>{line}</li>)}</ul>
          </Box>
          {!open.length&&<Alert severity="info" sx={{mt:2}}>No open loop program has five eligible surveys for this metric.</Alert>}
          {!closed.length&&<Alert severity="info" sx={{mt:2}}>No closed loop program has five eligible surveys for this metric.</Alert>}
          {(plots.length>0)&&<>
            {plots.map(({mode,label,plot,select})=><Box key={mode} sx={{mt:3,minWidth:0}}>
              <MDTypography variant="h5">{label}</MDTypography>
              <ComparisonChart plot={plot} onProgramClick={select} label={`${selected.label} ${label.toLowerCase()} program comparison`}/>
              <Box sx={{display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(min(100%, 240px), 1fr))',gap:2,minWidth:0}}>
                {plot.programs.map(({condition,title,position,countLabel,settings},index)=>{
                  const details=stimulationDetailRows(condition,participant);
                  return <Box component="section" aria-label={`${title} settings`} key={`${condition.id}-${index}`} sx={{p:2,border:'1px solid #e1e6ef',borderRadius:2,minWidth:0,overflowWrap:'anywhere'}}>
                  <MDTypography variant="h6">{title}{position===3 && rankedSelection?` · ${chosen.label}`: ''}</MDTypography>
                  {position<3&&<Button size="small" aria-label={`Compare ${title} for ${selected.label}`} onClick={()=>select(condition.id)}>Compare</Button>}
                  <MDTypography variant="body2">{countLabel}</MDTypography>
                  <MDTypography variant="body2">{condition.count?`Median ${condition.median}`:'No eligible surveys'}</MDTypography>
                  <Box sx={{mt:1}}>{(settings.length?settings:['Settings not available']).map((line,i)=><MDTypography component="div" variant="body2" key={i}>{line}</MDTypography>)}</Box>
                  {details.length>0&&<details style={{marginTop:12}}><summary>All recorded settings</summary><ul style={{paddingLeft:20}}>{details.map((line,i)=><li key={i}>{line}</li>)}</ul></details>}
                </Box>;})}
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
