import {useCallback,useMemo,useState} from 'react';
import {Alert,Autocomplete,Button,Card,FormControlLabel,Stack,Switch,TextField} from '@mui/material';
import MDTypography from 'components/MDTypography';
import {filterPoints,localTime,past28Range,unknownIntervalsInRange} from './data';
import {NEURAL_METRICS} from './neuralTimelineData';
import NeuralChart from './NeuralChart';
import StimulationContext from './StimulationContext';

const EMPTY=[];
export default function NeuralData({participant,phases=EMPTY,homeTransitions=EMPTY,unknownIntervals=EMPTY}) {
  const [range,setRange]=useState(null),[selected,setSelected]=useState(NEURAL_METRICS.map(m=>m.key));
  const [context,setContext]=useState(true),[selectedId,setSelectedId]=useState(''),[expanded,setExpanded]=useState(false);
  const choose=useCallback(id=>{setSelectedId(id);setExpanded(true);setContext(true);},[]);
  const today=localTime(Date.now()/1000).slice(0,10);
  const homes=useMemo(()=>homeTransitions.filter(e=>Number.isFinite(e.time)).slice().sort((a,b)=>a.time-b.time),[homeTransitions]);
  const defaults=useMemo(()=>({start:homes.length?localTime(homes[0].time).slice(0,10):today,end:today}),[homes,today]);
  const dates=range||defaults,recent=past28Range(today);
  const valid=Boolean(dates.start&&dates.end&&dates.start<=dates.end&&dates.end<=today);
  const prior=homes.filter(e=>localTime(e.time).slice(0,10)<dates.start).slice(-1)[0];
  const inWindow=useMemo(()=>valid?filterPoints(homes,dates.start,dates.end):EMPTY,[valid,homes,dates]);
  const records=useMemo(()=>(prior?[prior,...inWindow]:inWindow).map((e,i)=>({...e,number:i+1})),[prior,inWindow]);
  const current=records.find(e=>e.id===selectedId)||records.at(-1);
  const transitions=useMemo(()=>context?(inWindow.length>12?(current&&inWindow.some(e=>e.id===current.id)?[{...current,number:records.findIndex(e=>e.id===current.id)+1}]:EMPTY):records.filter(e=>inWindow.some(w=>w.id===e.id))):EMPTY,[context,inWindow,current,records]);
  const shown=selected.map(key=>NEURAL_METRICS.find(m=>m.key===key));
  return <Stack spacing={3}>
    <Card sx={{p:{xs:2,md:3},minWidth:0}}><Stack spacing={2}>
      <MDTypography variant="h4">Stim Program Settings</MDTypography>
      <MDTypography variant="body2">At-home stimulation settings across the study. Clinic test sweeps are excluded; reviewed final post-visit home programs are retained. Hover or click an observation for complete settings.</MDTypography>
      <Autocomplete multiple disableCloseOnSelect options={NEURAL_METRICS} value={shown} getOptionLabel={m=>m.label} isOptionEqualToValue={(a,b)=>a.key===b.key} onChange={(_,items)=>setSelected(items.map(m=>m.key))} renderInput={params=><TextField {...params} label="Settings to display"/>}/>
      <Stack direction="row" flexWrap="wrap" gap={2} alignItems="center">
        <TextField type="date" label="From" value={dates.start} InputLabelProps={{shrink:true}} onChange={e=>setRange({...dates,start:e.target.value})}/>
        <TextField type="date" label="Through" value={dates.end} inputProps={{max:today}} InputLabelProps={{shrink:true}} onChange={e=>setRange({...dates,end:e.target.value})}/>
        <Button onClick={()=>setRange(null)}>Full settings history</Button><Button onClick={()=>setSelected(NEURAL_METRICS.map(m=>m.key))}>Default settings</Button>
        <FormControlLabel control={<Switch checked={dates.start===recent.start&&dates.end===recent.end} onChange={e=>setRange(e.target.checked?recent:null)}/>} label="Past 28 days"/>
        <FormControlLabel control={<Switch checked={context} onChange={e=>setContext(e.target.checked)}/>} label="Stimulation context"/>
      </Stack>
      <MDTypography variant="body2">Connected steps join the last recorded home settings; they do not establish continuous delivery or exact activation times. Missing-evidence intervals stay blank. Open diamonds mark dates whose exact observation time was not recorded.</MDTypography>
      <MDTypography variant="body2">Mode and cycling describe the device/group. Only frequency, amplitude and pulse width have separate left/right traces. Closed-loop amplitude shows configured lower and upper limits; fixed or paused programs show their recorded amplitude.</MDTypography>
    </Stack></Card>
    {!valid?<Alert severity="warning">Choose valid dates with From on or before Through, and Through no later than today.</Alert>:<>
      {!homes.length&&<Alert severity="info">No reviewed home-program records are available for this participant.</Alert>}
      {unknownIntervalsInRange(unknownIntervals,dates).length>0&&<Alert severity="info">Home settings are not established for part of this period. The plots do not carry settings through those gaps.</Alert>}
      {context&&<StimulationContext events={records} selected={current} onSelect={choose} previous={prior} limited={inWindow.length>12} openDetails={expanded} onDetailsChange={setExpanded}/>}
      {!shown.length&&<Alert severity="info">Select a setting above to display its timeline.</Alert>}
      {homes.length>0&&shown.map(metric=><Card key={metric.key} sx={{p:{xs:1,md:3},minWidth:0}}>
        <Stack direction="row" justifyContent="space-between" flexWrap="wrap" gap={1} px={1}><MDTypography variant="h4">{metric.label}</MDTypography><MDTypography variant="body2">{inWindow.length} home-program records{prior?' · prior record included for context':''}</MDTypography></Stack>
        <NeuralChart metric={metric} events={homes} range={dates} participant={participant} phases={phases} unknownIntervals={unknownIntervals} transitions={transitions} onSelect={choose}/>
      </Card>)}
    </>}
  </Stack>;
}
