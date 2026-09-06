import {Alert,Card,Stack} from '@mui/material';
import MDTypography from 'components/MDTypography';
import ComparisonChart from './ComparisonChart';
import TrialPhaseLegend from './TrialPhaseLegend';
import {localTime} from './data';
import {comparisonCoverage,medicationConditionPlot,medicationTimeline,orderedMedicationConditions} from './comparisonData';

export default function Medications({comparison,metrics,today,phases}) {
  if(!comparison?.available) return <Alert severity="info">{comparison?.message || 'Medication comparisons are not available for this participant.'}</Alert>;
  const timeline = medicationTimeline(comparison.episodes,today,comparison.provenance?.period_start,phases);
  const phaseRange = {start:Number.isFinite(comparison.provenance?.period_start)?localTime(comparison.provenance.period_start).slice(0,10):timeline.traces.flatMap(t=>t.x).sort()[0]?.slice(0,10),end:today};
  return <Stack spacing={3}>
    <Alert severity="info">Stage 1 onward · Documented medication availability and regimens. PRN availability does not confirm that a dose was taken. Regimens may overlap, and the same survey can contribute to more than one condition; these comparisons do not isolate a medication effect.</Alert>
    <MDTypography variant="body2">{comparisonCoverage(comparison.provenance,true)}</MDTypography>
    <Card sx={{p:3}}><MDTypography variant="h4">Medication timeline</MDTypography>
      <MDTypography variant="body2">Thicker lines show primary regimens; thinner lines show supportive treatments. Dotted lines indicate PRN availability. Arrows mark earlier starts or ongoing regimens; an open diamond marks a known endpoint when the other date is missing.</MDTypography>
      {comparison.episodes.length?<><TrialPhaseLegend phases={phases} range={phaseRange}/><ComparisonChart plot={timeline} label="Documented medication regimens over time"/>
        <details><summary>All documented medication regimens</summary><ul>{comparison.episodes.map(episode=><li key={episode.id}>{episode.drug_class} · {episode.name} · {episode.dose} · {episode.frequency}{episode.prn?' · PRN available':''}</li>)}</ul></details>
      </>:<Alert severity="info">No documented medication intervals are available.</Alert>}
    </Card>
    {!metrics.length&&<Alert severity="info">Select a clinical metric above to compare medication conditions.</Alert>}
    {metrics.map(selected=>{
      const metric=comparison.metrics.find(item=>item.key===selected.key);
      const conditions=metric?.conditions || [];
      const ordered=orderedMedicationConditions(conditions);
      return <Card key={selected.key} sx={{p:3}}><MDTypography variant="h4">{selected.label}</MDTypography>
        <MDTypography variant="body2">All recorded conditions, grouped by drug class and regimen. Solid dark lines mark medians; boxes span the middle 50% of survey scores. Dots show individual eligible surveys; no top-three selection is applied.</MDTypography>
        {ordered.length?<><ComparisonChart plot={medicationConditionPlot(metric,ordered)} label={`${selected.label} medication conditions`}/>
          <details><summary>Condition details and survey counts</summary><ol>{ordered.map(condition=><li key={condition.id}>{condition.drug_class} · {condition.label} · {condition.count} surveys · median {condition.median}</li>)}</ol></details>
        </>:<Alert severity="info">No eligible medication-condition surveys for this metric.</Alert>}
      </Card>;
    })}
  </Stack>;
}
