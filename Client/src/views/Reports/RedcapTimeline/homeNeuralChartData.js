import {escapeText, tooltipText, localTime} from './data';
import {displayTarget, displayTargetText} from 'utils/participantTargets';

export const HOME_NEURAL_COLORS = {power:'#356E9B', amplitude:'#B86C2D', threshold:'#768299'};
const MAX_GUIDE_GAP_SECONDS = 20 * 60;
const finite = value => typeof value === 'number' && Number.isFinite(value);

// The API uses Unix seconds. ISO timestamps are accepted for exported fixtures;
// numeric strings and absent times are never silently treated as epoch zero.
export function neuralTime(value) {
  if (finite(value)) return value;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value)) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed / 1000 : null;
}

export function neuralSourceLabel(side, participant) {
  return ['left','right'].includes(side)
    ? displayTarget(participant,side,side === 'left' ? 'Left lead' : 'Right lead')
    : 'Sensing source unresolved';
}

// Contact pairs are categorical electrode identifiers, not a numeric range.
// Apply this only to sensing-contact display fields; keep API/source values intact.
export function neuralContactLabel(value) {
  if (typeof value !== 'string' || !value.trim()) return 'Contacts not recorded';
  const words = ['ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE','TEN','ELEVEN','TWELVE','THIRTEEN','FOURTEEN','FIFTEEN'];
  const pair = value.match(/^([A-Z]+)_([A-Z]+)_(?:LEFT|RIGHT)$/);
  if (pair && words.includes(pair[1]) && words.includes(pair[2]))
    return `${words.indexOf(pair[1])} and ${words.indexOf(pair[2])}`;
  return value.replace(/\b(\d+)\s*[–-]\s*(\d+)\b/g, '$1 and $2');
}

export function neuralScheduleLabel(provenance) {
  if (!provenance) return '';
  if (provenance.status === 'recorded' && provenance.metadata_available === true
      && provenance.conflicting_settings === false && provenance.inherited_settings === false)
    return 'Sensing labels follow the recorded schedule.';
  const reasons = [];
  if (provenance.conflicting_settings) reasons.push('earlier and later exported sensing settings differ; the exact change time is not established; Prasad’s selected labels are retained');
  if (provenance.inherited_settings) reasons.push('labels are inherited without a direct settings record for this interval');
  if (!provenance.metadata_available) reasons.push('complete schedule provenance is unavailable');
  return `Unverified sensing labels: ${reasons.join('; ') || 'schedule status is unresolved'}.`;
}

// Source enums describe missing associations, not measured neural values.
const absentSetting = value => typeof value !== 'string' || !value.trim()
  || /^(unknown|unavailable|not established|not recorded|recorded)$/i.test(value.trim());
export const neuralModeLabel = (value, participant) => absentSetting(value)
  ? 'Stimulation mode not linked to this recording' : displayTargetText(participant,value);
export const neuralMappingLabel = (value, participant) => value === 'source_recorded'
  ? 'Control relationship recorded in linked source configuration' : absentSetting(value)
  ? 'Sensing-to-stimulation control relationship not established' : displayTargetText(participant,value);
export const neuralThresholdLabel = (value, participant) => value === 'source_recorded'
  ? 'Configured thresholds are in linked source settings; interval-wide activation is not established.'
  : value === 'not_configured' ? 'Control thresholds are not configured in the linked source settings.' : absentSetting(value)
  ? 'Control thresholds are not linked to this recording.' : displayTargetText(participant,value);
const hasSettingRows = settings => ['group','left','right'].some(side => (settings?.[side] || []).length > 0);
export const hasNeuralSettings = segment => hasSettingRows(segment.settings)
  || (segment.settings_context?.observations || []).some(observation => hasSettingRows(observation.settings));
export const neuralDetailsLabel = segment => hasNeuralSettings(segment) ? 'Recorded settings and sensing details' : 'Sensing details';

export function neuralSegmentDescription(segment, participant) {
  const source = neuralSourceLabel(segment.sensing_side,participant);
  const contacts = neuralContactLabel(segment.sensing_contacts);
  const recordedCenter = segment.power_band_label?.match(/\b\d+(?:\.\d+)? Hz center\b/i)?.[0];
  const center = finite(segment.center_frequency_hz)
    ? `${segment.center_frequency_hz} Hz center` : recordedCenter || 'Center frequency not recorded';
  // A center frequency alone does not establish a power-band width.
  const band = segment.power_band_label || (finite(segment.center_frequency_hz)
    ? `${segment.center_frequency_hz} Hz center · band width not recorded` : 'Power band not recorded');
  const mode = neuralModeLabel(segment.mode,participant);
  const schedule = neuralScheduleLabel(segment.sensing_provenance);
  const unverified = schedule.startsWith('Unverified');
  const label = value => unverified ? `${value} (unverified)` : value;
  // A disagreement between the earlier/later contact or frequency settings does
  // not make the recorded lead itself unknown. Missing/inherited schedule
  // evidence still qualifies the source as well as the selected sensing labels.
  const sourceUnverified = unverified && (segment.sensing_provenance?.inherited_settings || !segment.sensing_provenance?.metadata_available);
  return {source:sourceUnverified ? label(source) : source, contacts:label(contacts), center:label(center), band:label(band), mode, schedule, sourceContextStatus:segment.settings_context?.status, hasSettings:hasNeuralSettings(segment), detailsLabel:neuralDetailsLabel(segment)};
}

export function neuralSettingsLines(segment, side, participant) {
  const programs = new Map();
  for (const row of segment.settings?.[side] || []) {
    const match = row.label.match(/^Program (\d+) · (.+)$/);
    const program = match ? match[1] : '', label = match ? match[2] : row.label;
    if (!programs.has(program)) programs.set(program,{});
    programs.get(program)[label] = String(row.value);
  }
  const target = neuralSourceLabel(side,participant), lines = [];
  for (const [program,rows] of programs) {
    lines.push(`${target}${program ? ` · Program ${program}` : ''} ${rows['Stimulation contacts'] || rows['Stimulation contacts (source)'] || (rows['Stimulation contacts (lead-local source)'] ? `lead-local source contacts ${rows['Stimulation contacts (lead-local source)']}` : 'Contacts not recorded')}`);
    const values = ['Frequency','Amplitude','Fixed / paused amplitude','Paused amplitude (configured)','Adaptive amplitude range','Adaptive minimum (configured)','Adaptive maximum (configured)','Pulse width']
      .filter(label=>rows[label] !== undefined).map(label=>label === 'Adaptive amplitude range' ? `range ${rows[label]}`
        : ['Fixed / paused amplitude','Paused amplitude (configured)'].includes(label) ? `paused ${rows[label]}`
          : label === 'Adaptive minimum (configured)' ? `configured minimum ${rows[label]}`
          : label === 'Adaptive maximum (configured)' ? `configured maximum ${rows[label]}` : rows[label]);
    if (values.length) lines.push(values.join(' · '));
    const thresholds = ['Lower threshold (configured)','Upper threshold (configured)']
      .filter(label=>rows[label] !== undefined).map(label=>`${label.startsWith('Lower') ? 'lower' : 'upper'} ${rows[label]}`);
    if (thresholds.length) lines.push(`Source-configured thresholds: ${thresholds.join(' · ')}`);
  }
  if (!programs.size) lines.push(segment.settings_context?.status === 'conflict'
    ? `${target} source configurations differ; inspect dated settings` : `${target} stimulation settings not recorded`);
  const group = (segment.settings?.group || []).filter(row=>['Group','Cycling'].includes(row.label));
  lines.push(...group.map(row=>`${row.label}: ${row.value}`));
  return lines;
}

export const neuralHoverLines = lines => lines.map(tooltipText).join('<br>');

export function homeNeuralPlot(panel, period, participant, maxGapSeconds = MAX_GUIDE_GAP_SECONDS) {
  const start = neuralTime(period.start), end = neuralTime(period.end);
  const observational = period.display_basis === 'recorded_observations';
  const powerLabel = observational ? 'Recorded neural power' : 'Biomarker';
  const amplitudeLabel = observational ? 'Recorded channel amplitude' : 'Stimulation amplitude';
  const independentCurrent = Array.isArray(panel.amplitude_series);
  const traces = [], descriptions = [];
  let observedPower = 0, observedAmplitude = 0, latestTime = null;
  for (const segment of panel.segments || []) {
    const segmentStart = neuralTime(segment.start), segmentEnd = neuralTime(segment.end);
    if (start === null || end === null || segmentStart === null || segmentEnd === null) continue;
    const a = Math.max(start,segmentStart), b = Math.min(end,segmentEnd);
    if (a >= b) continue;
    const description = neuralSegmentDescription(segment,participant);
    const hasDatedSources = (segment.settings_context?.observations || []).length > 0;
    const points = (segment.points || []).map(point=>({...point,time:neuralTime(point.time)}))
      .filter(point=>point.time !== null && point.time >= a && point.time < b)
      .sort((p,q)=>p.time-q.time);
    // Empty settings boundaries remain available in the source selector; only
    // intervals with actual plotted observations belong in the visible key.
    if (points.some(point => (finite(point.power) && !point.power_conflict) || (!independentCurrent && finite(point.amplitude) && !point.amplitude_conflict))) {
    descriptions.push({id:segment.id,start:a,end:b,...description,
      mappingStatus:neuralMappingLabel(segment.control_mapping || segment.mapping_status,participant),
      thresholdStatus:neuralThresholdLabel(segment.threshold_status,participant)});
    }
    const sensingOnly = /sensing[ _-]*only/i.test(description.mode);
    const thresholdLines = (sensingOnly ? [] : segment.thresholds || []).filter(threshold=>finite(threshold.value))
      .map(threshold=>`${threshold.label || 'Configured threshold'}: ${threshold.value} LSB`);
    const detail = neuralHoverLines([...neuralSettingsLines(segment,panel.side,participant),
      `Mode: ${description.mode}`,`Adaptive state: ${absentSetting(segment.adaptive_state) ? (hasDatedSources ? 'Per-sample delivery unverified; dated source observation states are in details' : segment.settings_context ? 'Delivery state is not established by the available source evidence' : 'Not linked to this recording') : segment.adaptive_state}`,
      `${observational ? 'Sensing source' : 'Biomarker source'}: ${description.source}`,`Sensing contacts: ${description.contacts}`,description.center,description.band,
      `Control mapping: ${neuralMappingLabel(segment.control_mapping || segment.mapping_status,participant)}`,
      ...(description.schedule ? [description.schedule] : []),...thresholdLines,
      neuralThresholdLabel(segment.threshold_status,participant),
      ...(segment.settings_context ? [hasDatedSources ? 'Linked report configuration; see details for source dates and activation limits.' : 'Source settings could not be verified; see details for the source gap.'] : []),
      `Click for ${neuralDetailsLabel(segment).toLowerCase()}`]);
    for (const metric of (independentCurrent ? ['power'] : ['power','amplitude'])) {
      const x = [], y = [], customdata = [];
      let previous = null, count = 0;
      for (const point of points) {
        // Use elapsed real time for gaps, before conversion to the local display
        // clock. Unknown/conflicting values interrupt the guide independently.
        if (previous !== null && point.time-previous > maxGapSeconds) {
          x.push(null); y.push(null); customdata.push(null);
        }
        const value = finite(point[metric]) && !point[`${metric}_conflict`] ? point[metric] : null;
        const power = finite(point.power) && !point.power_conflict ? `${point.power} LSB` : 'Not established';
        const amplitude = !independentCurrent && finite(point.amplitude) && !point.amplitude_conflict ? `${point.amplitude} mA` : 'Not established';
        x.push(localTime(point.time)); y.push(value);
        customdata.push([segment.id,`${escapeText(localTime(point.time))} · Pacific<br>${powerLabel}: ${escapeText(power)}<br>${independentCurrent ? 'Current shown separately at its own recorded times' : `${amplitudeLabel}: ${escapeText(amplitude)}`}<br>${detail}`]);
        if (value !== null) {count++;latestTime = latestTime === null ? point.time : Math.max(latestTime,point.time);}
        previous = point.time;
      }
      if (metric === 'power') observedPower += count;
      else observedAmplitude += count;
      if (!count) continue;
      traces.push({type:'scatter',mode:'lines+markers',name:metric === 'power' ? `${description.source} ${observational ? 'recorded neural power' : 'biomarker'}` : `${neuralSourceLabel(panel.side,participant)} ${observational ? 'recorded channel amplitude' : 'stimulation amplitude'}`,
        x,y,customdata,yaxis:metric === 'power' ? 'y' : 'y2',connectgaps:false,showlegend:false,
        line:{color:HOME_NEURAL_COLORS[metric],width:1.5},marker:{color:HOME_NEURAL_COLORS[metric],size:4},
        hovertemplate:'%{customdata[1]}<extra></extra>'});
    }
    // Guides represent the recorded controller configuration, not a fitted
    // threshold or evidence of delivery. Sensing-only has no control threshold.
    for (const [index,threshold] of (sensingOnly ? [] : segment.thresholds || []).entries()) {
      if (!finite(threshold.value)) continue;
      const label = threshold.label || 'Configured threshold';
      traces.push({type:'scatter',mode:'lines',name:escapeText(label),x:[localTime(a),localTime(b)],y:[threshold.value,threshold.value],
        yaxis:'y',showlegend:false,connectgaps:false,line:{color:HOME_NEURAL_COLORS.threshold,width:1.5,dash:index === 0 ? 'dash' : 'dot'},
        customdata:[[segment.id,detail],[segment.id,detail]],
        hovertemplate:`${escapeText(label)}: %{y} LSB<br>%{customdata[1]}<extra></extra>`});
    }
  }
  if (independentCurrent && start !== null && end !== null) {
    const points = panel.amplitude_series.map(point=>({...point,time:neuralTime(point.time)}))
      .filter(point=>point.time !== null && point.time >= start && point.time < end).sort((p,q)=>p.time-q.time);
    const x=[],y=[],customdata=[];
    let previous=null;
    for (const point of points) {
      if (previous !== null && point.time-previous > maxGapSeconds) {x.push(null);y.push(null);customdata.push(null);}
      const value=finite(point.amplitude) && !point.amplitude_conflict ? point.amplitude : null;
      x.push(localTime(point.time));y.push(value);
      customdata.push([null,neuralHoverLines([`${localTime(point.time)} · Pacific`,
        `${neuralSourceLabel(panel.side,participant)} recorded current: ${value === null ? 'Unknown / conflicting' : `${value} mA`}`,
        panel.amplitude_provenance || 'Recorded current on this lead; no power-to-current alignment inferred.'])]);
      if (value !== null) {observedAmplitude++;latestTime=latestTime === null ? point.time : Math.max(latestTime,point.time);}
      previous=point.time;
    }
    if (observedAmplitude) traces.push({type:'scatter',mode:'lines+markers',name:`${neuralSourceLabel(panel.side,participant)} recorded current`,
      x,y,customdata,yaxis:'y2',connectgaps:false,showlegend:false,
      line:{color:HOME_NEURAL_COLORS.amplitude,width:1.5},marker:{color:HOME_NEURAL_COLORS.amplitude,size:4},
      hovertemplate:'%{customdata[1]}<extra></extra>'});
  }
  return {traces,descriptions,observedPower,observedAmplitude,latestTime};
}

export function homeNeuralLayout(period, width = 0) {
  const compact = width > 0 && width < 600;
  const start = neuralTime(period.start), end = neuralTime(period.end);
  return {autosize:true,height:compact ? 360 : 390,margin:{l:compact ? 59 : 76,r:compact ? 55 : 70,t:18,b:65},
    paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Roboto, sans-serif',color:'#344767',size:compact ? 12 : 14},
    xaxis:{type:'date',...(start !== null && end !== null ? {range:[localTime(start),localTime(end)]} : {}),
      title:{text:'Date · Pacific time',standoff:12},nticks:compact ? 3 : 7,automargin:true,gridcolor:'#edf0f4'},
    yaxis:{title:{text:'Biomarker (LSB)',standoff:8},automargin:true,zeroline:false,gridcolor:'#edf0f4',color:HOME_NEURAL_COLORS.power},
    yaxis2:{title:{text:'Stim amp (mA)',standoff:8},overlaying:'y',side:'right',automargin:true,showgrid:false,zeroline:false,rangemode:'tozero',color:HOME_NEURAL_COLORS.amplitude},
    hovermode:'closest',showlegend:false,hoverlabel:{align:'left'},uirevision:`${period.id}:${period.start}:${period.end}`};
}
