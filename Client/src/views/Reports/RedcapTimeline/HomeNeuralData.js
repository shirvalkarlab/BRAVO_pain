import {useState} from 'react';
import {Accordion, AccordionDetails, AccordionSummary, Alert, Autocomplete, Button, Card, Chip, Stack, TextField} from '@mui/material';
import MDTypography from 'components/MDTypography';
import {displayTarget, displayTargetText} from 'utils/participantTargets';
import {localTime} from './data';
import {useHomeNeuralTimeline} from './useHomeNeuralTimeline';
import HomeNeuralChart from './HomeNeuralChart';
import {homeNeuralPlot, neuralContactLabel, neuralSegmentDescription, neuralScheduleLabel} from './homeNeuralChartData';

const EMPTY = [];
const periodName = id => id === 'current' ? 'Current' : id === 'previous' ? 'Previous' : 'Selected';
const stamp = time => localTime(time).replace('T', ' ').slice(0, 16);
const target = (participant, side) => displayTarget(participant, side, side === 'left' ? 'Left' : 'Right');
const title = (segment, participant) => {
  const {source,contacts,center,mode} = neuralSegmentDescription(segment,participant);
  return `${stamp(segment.start)} · ${source} · contacts ${contacts} · ${center} · ${mode}`;
};

function SettingsDetails({segment, participant}) {
  return <Stack spacing={2}>
    <MDTypography variant="body2">{displayTargetText(participant,segment.evidence)}</MDTypography>
    {segment.sensing_provenance && <Alert severity={segment.sensing_provenance.status === 'recorded' ? 'info' : 'warning'}>{neuralScheduleLabel(segment.sensing_provenance)}</Alert>}
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

export function NeuralSettingsSelector({segments,selected,participant,open,setOpen,choose,observational=false,hasRecordedCurrent=false}) {
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
    </Stack> : <Alert severity="info">{hasRecordedCurrent ? 'Recorded lead current is shown; no sensing settings interval is available for this side in this period.' : observational ? 'No recorded neural observations for this channel in this period.' : 'No eligible home recordings for this side in this visit period.'}</Alert>;
}

function NeuralPanel({panel, window, participant, scoped, observational=false}) {
  const [selection,setSelection] = useState(null), [open,setOpen] = useState(false);
  const segments = panel.segments;
  const selected = segments.find(s => s.id === selection) || segments.at(-1);
  const choose = id => {setSelection(id);setOpen(true);};
  return <Card sx={{p:{xs:1,md:3},minWidth:0}}>
    <Stack spacing={1} px={1}>
      <MDTypography variant="h5">{target(participant,panel.side)} · {observational ? 'recorded neural power and channel amplitude' : 'biomarker and stimulation'}</MDTypography>
      <MDTypography variant="body2">{Array.isArray(panel.amplitude_series) ? "Blue: native recorded neural power, left axis. Orange: this lead’s recorded current at its own sample times, right axis. The controlling relationship is not inferred." : scoped ? "Blue: native recorded neural power, left axis. Orange: amplitude recorded with this channel, right axis. The controlling stimulation side is not inferred." : "Blue: recorded biomarker power, left axis. Orange: this side’s recorded amplitude, right axis. The biomarker’s source can be on the opposite side."}</MDTypography>
    </Stack>
    <HomeNeuralChart panel={panel} window={window} participant={participant} onSegment={choose}/>
    <NeuralSettingsSelector segments={segments} selected={selected} participant={participant} open={open} setOpen={setOpen} choose={choose} observational={observational} hasRecordedCurrent={homeNeuralPlot(panel,window,participant).observedAmplitude > 0}/>
  </Card>;
}

export function NeuralAnalysisPolicy({policy}) {
  if (policy?.id !== 'prasad_chronic_v1' || policy.exact_zero_power_excluded !== true
      || policy.invalid_code_power_excluded !== true || policy.raw_values_preserved !== true) return null;
  return <Alert severity="info">Prasad’s analysis policy excludes exact-zero chronic power and device-invalid power codes from these views. This is an analysis exclusion, not evidence that zero is physiologically invalid. Raw recordings and zero-current readings are preserved.</Alert>;
}

const continuingHome = provenance => provenance?.home_status === 'assumed_continuing_home'
  && ['operator_confirmed_no_new_stimulation_visits','documented_stimulation_calendar'].includes(provenance.home_status_basis);

export function ObservationProvenance({provenance}) {
  if (!provenance) return null;
  const labels={stored_snapshot:'Latest stored clinic snapshot', unavailable:'Clinic snapshot unavailable', invalid:'Clinic snapshot could not be verified'};
  const built=typeof provenance.calendar_built_at === 'string' ? Date.parse(provenance.calendar_built_at) : NaN;
  return <Alert severity="info">
    {labels[provenance.calendar_status] || 'Clinic snapshot status unknown'}.
    {Number.isFinite(built) && <> Snapshot prepared: {stamp(built/1000)} Pacific.</>}
    {' '}A stored snapshot does not confirm the latest upstream sync succeeded.
    {continuingHome(provenance)
      ? <> Home period assumed to continue: {provenance.home_status_basis === 'operator_confirmed_no_new_stimulation_visits'
        ? <>the study operator confirmed no intervening stimulation visits{provenance.home_status_confirmed_through && <> through {provenance.home_status_confirmed_through}</>}</>
        : <>the last documented stimulation session{provenance.last_documented_stimulation_date && <> was {provenance.last_documented_stimulation_date}</>}; this updated calendar supersedes the earlier no-new-visits confirmation</>}. A clinic sheet or weekly stimulation summary documenting a new session ends this continuity assumption. Physical location is not independently verified; sensing settings retain their own source labels.</>
      : <> Testing-calendar completeness, physical location and at-home status remain unverified.</>}
    {provenance.message && <> {provenance.message}</>}
  </Alert>;
}

export default function HomeNeuralData({participant,refreshRevision=0}) {
  const [revision,setRevision] = useState(0);
  const query = useHomeNeuralTimeline(participant,[refreshRevision,revision],undefined,true);
  const windows = query.data?.windows || EMPTY;
  const scope = query.data?.neural_scope;
  const observationScope = query.data?.observation_scope;
  const observations = (query.data?.observation_windows || EMPTY)
    .filter(period=>period.display_basis === 'recorded_observations')
    .map(period=>({...period,panels:period.panels.filter(panel=>{
      const plotted=homeNeuralPlot(panel,period,participant);
      return plotted.observedPower > 0 || plotted.observedAmplitude > 0;
    })}))
    .filter(period=>period.panels.length > 0);
  return <Stack spacing={3}>
    <Card sx={{p:{xs:2,md:3},minWidth:0}}><Stack spacing={2}>
      <Stack direction="row" flexWrap="wrap" justifyContent="space-between" gap={2}>
        <MDTypography variant="h4">Neural Data</MDTypography>
        <Button variant="outlined" disabled={query.loading} onClick={()=>setRevision(r=>r+1)}>Refresh neural view</Button>
      </Stack>
      <MDTypography variant="body1">{observations.length ? "Recent recorded neural observations and separately reviewed historical periods." : scope ? "Recorded neural power and stimulation amplitude within the reviewed historical range." : "At-home biomarker power and stimulation amplitude during the current and previous stimulation-visit periods."}</MDTypography>
      <MDTypography variant="body2">Each device record summarizes approximately 10 minutes. These are stored averages, not a continuous stream or a promise of transmission every 10 minutes. Threshold lines show recorded control settings; averaged power cannot reveal every threshold crossing.</MDTypography>
      <MDTypography variant="body2">For reviewed historical periods, Current means the most recent reviewed stimulation visit to the present. Previous means the preceding visit up to that visit. Clinic-testing dates and overlapping averaging bins are excluded because exact clinic departure times are not established. Dates and times are Pacific.</MDTypography>
      <MDTypography variant="body2">{scope ? "Panels retain the recorded channel side, contacts and frequency. A controlling stimulation side or threshold is not inferred. Missing data and unresolved settings remain gaps." : "Each panel follows the stimulated side. Biomarker labels identify the actual sensing side, contacts and frequency; contralateral control is shown explicitly. Sensing-only periods have no active control threshold. Unavailable values and unknown settings remain gaps. Settings are tied to source observations; snapshot times do not establish exact activation times."}</MDTypography>
    </Stack></Card>
    {scope && <Alert severity="info">
      Reviewed historical range: {stamp(scope.coverage_start)} → {stamp(scope.coverage_end)} Pacific (end excluded).
      {' '}{scope.description} These observations do not verify physical location. Dates outside this range have not been reviewed here.
    </Alert>}
    {query.loading && <MDTypography role="status">Loading neural recordings…</MDTypography>}
    {query.error && <Alert severity="error">{query.error}</Alert>}
    {query.freshnessError && <Alert severity="warning">{query.freshnessError}</Alert>}
    <ObservationProvenance provenance={query.data?.observation_provenance}/>
    <NeuralAnalysisPolicy policy={query.data?.chronic_analysis_policy}/>
    {query.data && !windows.length && <Alert severity="info">{query.data.message || 'A reviewed stimulation-visit calendar is needed to define these periods.'}</Alert>}
    {observations.length > 0 && <Stack spacing={2} component="section" aria-label="Recent recorded observations">
      <MDTypography variant="h4">Recent recorded observations · latest imported data</MDTypography>
      <Alert severity="info">{continuingHome(query.data?.observation_provenance)
        ? 'These recorded observations use the continuing-home assumption described above. Physical location is not independently verified; this assumption does not establish sensing contacts or a controlling stimulation relationship.'
        : 'Physical location and at-home status are unverified, and the testing calendar may be incomplete. These plots show recorded observations, not a reviewed at-home analysis.'} Known testing days and overlapping averaging bins are excluded.</Alert>
      {observationScope && <MDTypography variant="body2">
        Date limits for this recent view: {stamp(observationScope.start)} → {stamp(observationScope.end)} Pacific (end excluded).
        {' '}{observationScope.description}
      </MDTypography>}
      {observations.map(period=><Stack key={`observed:${period.id}:${period.start}:${period.end}:${revision}`} spacing={2} component="section" aria-label={`${period.id} recorded observations`}>
        <Stack direction="row" alignItems="baseline" flexWrap="wrap" gap={2}>
          <MDTypography variant="h5">{periodName(period.id)} observations</MDTypography>
          <Chip label={`Requested period: ${stamp(period.start)} → ${stamp(period.end)} Pacific`} variant="outlined" sx={{height:'auto','& .MuiChip-label':{whiteSpace:'normal',py:1}}}/>
        </Stack>
        <MDTypography variant="body2">{period.label}</MDTypography>
        {period.coverage_basis === 'recorded_sample_envelope' && period.coverage?.start != null && period.coverage?.end != null && <MDTypography variant="body2">Recorded coverage: {stamp(period.coverage.start)} → {stamp(period.coverage.end)} Pacific. This is the range of available observations, not evidence of continuous recording.</MDTypography>}
        {period.panels.map(panel=><NeuralPanel key={panel.side} panel={panel} window={period} participant={participant} scoped observational/>)}
      </Stack>)}
    </Stack>}
    {observations.length > 0 && windows.length > 0 && <MDTypography variant="h4">Reviewed historical periods</MDTypography>}
    {windows.map(period=><Stack key={`${period.id}:${period.start}:${period.end}:${revision}`} spacing={2} component="section" aria-label={`${period.id} stimulation visit period`}>
      <Stack direction="row" alignItems="baseline" flexWrap="wrap" gap={2}>
        <MDTypography variant="h4">{periodName(period.id)} visit period</MDTypography>
        <Chip label={`${stamp(period.start)} → ${stamp(period.end)} Pacific`} variant="outlined" sx={{height:'auto','& .MuiChip-label':{whiteSpace:'normal',py:1}}}/>
      </Stack>
      {period.coverage?.status === 'outside'
        ? <Alert severity="info">This visit period is outside the reviewed historical range. Its dates have not been changed; any supported previous period is shown below.</Alert>
        : <>
          {period.coverage?.status === 'partial' && <Alert severity="info">Only {stamp(period.coverage.start)} → {stamp(period.coverage.end)} Pacific is within the reviewed range for this period; the remaining dates are unavailable.</Alert>}
          {period.panels.map(panel=><NeuralPanel key={panel.side} panel={panel} window={period} participant={participant} scoped={!!scope}/>)}
        </>}
    </Stack>)}
    {query.data && windows.length === 1 && <Alert severity="info">Only one reviewed stimulation visit is available; no previous visit period can be defined.</Alert>}
  </Stack>;
}
