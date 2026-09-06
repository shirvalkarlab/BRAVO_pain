import {useState} from 'react';
import {Accordion, AccordionDetails, AccordionSummary, Alert, Autocomplete, Button, Card, Chip, Stack, TextField} from '@mui/material';
import MDTypography from 'components/MDTypography';
import {displayTarget, displayTargetText} from 'utils/participantTargets';
import {localTime} from './data';
import {useHomeNeuralTimeline} from './useHomeNeuralTimeline';
import HomeNeuralChart from './HomeNeuralChart';
import {neuralContactLabel, neuralSegmentDescription} from './homeNeuralChartData';

const EMPTY = [];
const stamp = time => localTime(time).replace('T', ' ').slice(0, 16);
const target = (participant, side) => displayTarget(participant, side, side === 'left' ? 'Left' : 'Right');
const title = (segment, participant) => {
  const {source,contacts,center,mode} = neuralSegmentDescription(segment,participant);
  return `${stamp(segment.start)} · ${source} · contacts ${contacts} · ${center} · ${mode}`;
};

function SettingsDetails({segment, participant}) {
  return <Stack spacing={2}>
    <MDTypography variant="body2">{displayTargetText(participant,segment.evidence)}</MDTypography>
    <MDTypography variant="body2">{displayTargetText(participant,segment.threshold_status)}</MDTypography>
    <Stack direction={{xs:'column', md:'row'}} gap={3}>
      {['group','left','right'].map(scope => <div key={scope} style={{flex:1,minWidth:0}}>
        <MDTypography variant="h6">{scope === 'group' ? 'Device / group' : target(participant, scope)}</MDTypography>
        <dl style={{margin:0,fontSize:14}}>{(segment.settings?.[scope] || EMPTY).map((row,i) => <div key={i} style={{padding:'7px 0',borderBottom:'1px solid #edf0f4'}}>
          <dt style={{color:'#526179',fontWeight:600}}>{row.label === 'Tablet target' ? 'Target' : row.label}</dt>
          <dd style={{margin:0,overflowWrap:'anywhere',whiteSpace:'pre-line'}}>{row.label === 'Tablet target' ? target(participant,scope)
            : row.label === 'Sensing source hemisphere' ? displayTarget(participant,row.value)
              : /Sensing contacts$/i.test(row.label) ? neuralContactLabel(row.value)
              : displayTargetText(participant,row.value)}</dd>
        </div>)}</dl>
      </div>)}
    </Stack>
  </Stack>;
}

export function NeuralSettingsSelector({segments,selected,participant,open,setOpen,choose}) {
  return selected ? <Stack spacing={1} px={1}>
      <Autocomplete disableClearable options={segments} value={selected} getOptionLabel={s=>title(s,participant)}
        isOptionEqualToValue={(a,b)=>a.id===b.id} onChange={(_,s)=>choose(s.id)}
        renderOption={(props,s)=><li {...props} key={s.id}>{title(s,participant)}</li>}
        renderInput={params=><TextField {...params} label="Recorded settings interval" helperText="Hover over the plot for details, or choose an interval here. Settings are tied to their source observation."/>}
        sx={{'& .MuiInputBase-root':{fontSize:14}}}/>
      <Accordion expanded={open} onChange={(_,value)=>setOpen(value)} disableGutters sx={{boxShadow:'none',border:'1px solid #e3e8ef'}}>
        <AccordionSummary expandIcon={<span aria-hidden="true">⌄</span>}><MDTypography variant="body2">{displayTargetText(participant,selected.mode)} · contacts, sensing, thresholds and complete settings</MDTypography></AccordionSummary>
        <AccordionDetails><SettingsDetails segment={selected} participant={participant}/></AccordionDetails>
      </Accordion>
    </Stack> : <Alert severity="info">No eligible home recordings for this side in this visit period.</Alert>;
}

function NeuralPanel({panel, window, participant}) {
  const [selection,setSelection] = useState(null), [open,setOpen] = useState(false);
  const segments = panel.segments;
  const selected = segments.find(s => s.id === selection) || segments.at(-1);
  const choose = id => {setSelection(id);setOpen(true);};
  return <Card sx={{p:{xs:1,md:3},minWidth:0}}>
    <Stack spacing={1} px={1}>
      <MDTypography variant="h5">{target(participant,panel.side)} · biomarker and stimulation</MDTypography>
      <MDTypography variant="body2">Blue: recorded biomarker power, left axis. Orange: this side’s recorded amplitude, right axis. The biomarker’s source can be on the opposite side.</MDTypography>
    </Stack>
    <HomeNeuralChart panel={panel} window={window} participant={participant} onSegment={choose}/>
    <NeuralSettingsSelector segments={segments} selected={selected} participant={participant} open={open} setOpen={setOpen} choose={choose}/>
  </Card>;
}

export default function HomeNeuralData({participant}) {
  const [revision,setRevision] = useState(0);
  const query = useHomeNeuralTimeline(participant,revision);
  const windows = query.data?.windows || EMPTY;
  return <Stack spacing={3}>
    <Card sx={{p:{xs:2,md:3},minWidth:0}}><Stack spacing={2}>
      <Stack direction="row" flexWrap="wrap" justifyContent="space-between" gap={2}>
        <MDTypography variant="h4">Neural Data</MDTypography>
        <Button variant="outlined" disabled={query.loading} onClick={()=>setRevision(r=>r+1)}>Refresh neural view</Button>
      </Stack>
      <MDTypography variant="body1">At-home biomarker power and stimulation amplitude during the current and previous stimulation-visit periods.</MDTypography>
      <MDTypography variant="body2">Each device record summarizes approximately 10 minutes. These are stored averages, not a continuous stream or a promise of transmission every 10 minutes. Threshold lines show recorded control settings; averaged power cannot reveal every threshold crossing.</MDTypography>
      <MDTypography variant="body2">Current: most recent reviewed stimulation visit to the present. Previous: the preceding visit up to that visit. Clinic-testing dates and overlapping averaging bins are excluded because exact clinic departure times are not established. Dates and times are Pacific.</MDTypography>
      <MDTypography variant="body2">Each panel follows the stimulated side. Biomarker labels identify the actual sensing side, contacts and frequency; contralateral control is shown explicitly. Sensing-only periods have no active control threshold. Unavailable values and unknown settings remain gaps. Settings are tied to source observations; snapshot times do not establish exact activation times.</MDTypography>
    </Stack></Card>
    {query.loading && <MDTypography role="status">Loading at-home neural recordings…</MDTypography>}
    {query.error && <Alert severity="error">{query.error}</Alert>}
    {query.data && !windows.length && <Alert severity="info">{query.data.message || 'A reviewed stimulation-visit calendar is needed to define these periods.'}</Alert>}
    {windows.map(period=><Stack key={`${period.id}:${period.start}:${period.end}:${revision}`} spacing={2} component="section" aria-label={`${period.id} stimulation visit period`}>
      <Stack direction="row" alignItems="baseline" flexWrap="wrap" gap={2}>
        <MDTypography variant="h4">{period.id === 'current' ? 'Current' : 'Previous'} visit period</MDTypography>
        <Chip label={`${stamp(period.start)} → ${stamp(period.end)} Pacific`} variant="outlined" sx={{height:'auto','& .MuiChip-label':{whiteSpace:'normal',py:1}}}/>
      </Stack>
      {period.panels.map(panel=><NeuralPanel key={panel.side} panel={panel} window={period} participant={participant}/>)}
    </Stack>)}
    {query.data && windows.length === 1 && <Alert severity="info">Only one reviewed stimulation visit is available; no previous visit period can be defined.</Alert>}
  </Stack>;
}
