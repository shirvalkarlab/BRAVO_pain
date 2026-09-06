import { currentTarget, currentTargetText, isRCS08Participant, routeParticipant } from "utils/participantTargets";
import {Accordion, AccordionDetails, AccordionSummary, Alert, Autocomplete, Card, Stack, TextField, createFilterOptions} from "@mui/material";
import MDTypography from "components/MDTypography";
import {eventTimeLabel} from "./data";

const eventLabel = event => `${event.number}. ${eventTimeLabel(event)} · ${event.label}`;
const filterEvents = createFilterOptions({limit: 100, stringify: eventLabel});

function SettingsList({rows, side}) {
  return <dl style={{margin: "8px 0", fontSize: 16}}>{rows.map((row, i) => <div key={i} style={{padding: "9px 0", borderBottom: "1px solid #edf0f4"}}>
    <dt style={{fontWeight: 600, color: "#526179"}}>{side && row.label === "Tablet target" && isRCS08Participant(routeParticipant()) ? "Target" : row.label}</dt>
    <dd style={{margin: "3px 0 0", overflowWrap: "anywhere", whiteSpace: "pre-line"}}>{side && row.label === "Tablet target" ? currentTarget(side, row.value) : row.label === "Sensing source hemisphere" ? currentTarget(row.value) : currentTargetText(row.value)}</dd>
  </div>)}</dl>;
}

export default function StimulationContext({events, selected, onSelect, previous, limited, openDetails = false, onDetailsChange}) {
  const sourceUrl = selected?.source_url;
  return <Card sx={{p: 3, mb: 3}}>
    <MDTypography variant="h4">Stimulation settings</MDTypography>
    <MDTypography variant="body2" sx={{my: 1}}>Red dashed lines mark reviewed home-program transitions. Open the settings below for all recorded details.</MDTypography>
    {previous && <MDTypography variant="body2" sx={{mb: 2}}>Last record before this window: {eventTimeLabel(previous)} · {previous.label}. This does not establish continuous delivery through the window.</MDTypography>}
    {!events.length ? <Alert severity="info">No home-program transitions are established in this period.</Alert> : <>
      <Autocomplete fullWidth disableClearable options={events} value={selected}
        getOptionLabel={eventLabel} isOptionEqualToValue={(a, b) => a.id === b.id} filterOptions={filterEvents}
        onChange={(_, event) => onSelect(event.id)}
        renderOption={(props, event) => <li {...props} key={event.id} style={{fontSize: 16, whiteSpace: "normal"}}>{eventLabel(event)}</li>}
        renderInput={params => <TextField {...params} label="Home-program transition"
          helperText={events.length > 100 ? `Showing up to 100 matches. Search by date, time, label or record number, or narrow the dates, to find any of these ${events.length.toLocaleString()} records.` : "Search by date, time, label or record number."} />}
        sx={{my: 2, "& .MuiInputBase-root": {fontSize: 16}}} />
      {limited && <Alert severity="info" sx={{mb: 2}}>{events.length} records fall in this window. To keep the graphs readable, they mark the selected record. Choose another record above or narrow the dates to show all lines (up to 12).</Alert>}
      <Accordion disableGutters expanded={openDetails} onChange={(_, expanded) => onDetailsChange(expanded)} sx={{boxShadow: "none", border: "1px solid #e3e8ef"}}>
        <AccordionSummary expandIcon={<span aria-hidden="true">⌄</span>}><MDTypography variant="h5">{selected.label} · complete settings</MDTypography></AccordionSummary>
        <AccordionDetails>
          <MDTypography variant="body2" sx={{mb: 2}}>{eventTimeLabel(selected)}. {selected.evidence}</MDTypography>
          {typeof sourceUrl === "string" && /^https:\/\//i.test(sourceUrl) && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Reviewed source</a>}
          <MDTypography variant="h6">Group settings · shared by both sides</MDTypography>
          <SettingsList rows={selected.settings.group} />
          <Stack direction={{xs: "column", md: "row"}} spacing={4} sx={{mt: 3}}>
            {[['left', 'Left'], ['right', 'Right']].map(([key, title]) => <div key={key} style={{flex: 1, minWidth: 0}}>
              <MDTypography variant="h5">{currentTarget(title)} · stimulation and sensing</MDTypography>
              <SettingsList rows={selected.settings[key]} side={key} />
            </div>)}
          </Stack>
        </AccordionDetails>
      </Accordion>
    </>}
  </Card>;
}
