import {escapeText, localTime} from './data';
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
  return value.replace(/\b(\d+)\s*[–-]\s*(\d+)\b/g, '$1 and $2');
}

export function neuralSegmentDescription(segment, participant) {
  const source = neuralSourceLabel(segment.sensing_side,participant);
  const contacts = neuralContactLabel(segment.sensing_contacts);
  const recordedCenter = segment.power_band_label?.match(/\b\d+(?:\.\d+)? Hz center\b/i)?.[0];
  const center = finite(segment.center_frequency_hz)
    ? `${segment.center_frequency_hz} Hz center` : recordedCenter || 'Center frequency not recorded';
  // A center frequency alone does not establish a power-band width.
  const band = segment.power_band_label || (finite(segment.center_frequency_hz)
    ? `${segment.center_frequency_hz} Hz center · band width not recorded` : 'Power band not recorded');
  const mode = displayTargetText(participant,segment.mode) || 'Mode not established';
  return {source, contacts, center, band, mode};
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
    lines.push(`${target}${program ? ` · Program ${program}` : ''} ${rows['Stimulation contacts'] || 'Contacts not recorded'}`);
    const values = ['Frequency','Amplitude','Fixed / paused amplitude','Adaptive amplitude range','Pulse width']
      .filter(label=>rows[label] !== undefined).map(label=>label === 'Adaptive amplitude range' ? `range ${rows[label]}`
        : label === 'Fixed / paused amplitude' ? `paused ${rows[label]}` : rows[label]);
    if (values.length) lines.push(values.join(' · '));
  }
  if (!programs.size) lines.push(`${target} stimulation settings not recorded`);
  const group = (segment.settings?.group || []).filter(row=>['Group','Cycling'].includes(row.label));
  lines.push(...group.map(row=>`${row.label}: ${row.value}`));
  return lines;
}

export const neuralHoverLines = lines => lines.map(line => (String(line).match(/.{1,42}(?:\s|$)|.{1,42}/g) || [''])
  .map(part=>escapeText(part.trim())).join('<br>')).join('<br>');

export function homeNeuralPlot(panel, period, participant, maxGapSeconds = MAX_GUIDE_GAP_SECONDS) {
  const start = neuralTime(period.start), end = neuralTime(period.end);
  const traces = [], descriptions = [];
  let observedPower = 0, observedAmplitude = 0, latestTime = null;
  for (const segment of panel.segments || []) {
    const segmentStart = neuralTime(segment.start), segmentEnd = neuralTime(segment.end);
    if (start === null || end === null || segmentStart === null || segmentEnd === null) continue;
    const a = Math.max(start,segmentStart), b = Math.min(end,segmentEnd);
    if (a >= b) continue;
    const description = neuralSegmentDescription(segment,participant);
    const points = (segment.points || []).map(point=>({...point,time:neuralTime(point.time)}))
      .filter(point=>point.time !== null && point.time >= a && point.time < b)
      .sort((p,q)=>p.time-q.time);
    // Empty settings boundaries remain available in the source selector; only
    // intervals with actual plotted observations belong in the visible key.
    if (points.some(point => (finite(point.power) && !point.power_conflict) || (finite(point.amplitude) && !point.amplitude_conflict))) {
    descriptions.push({id:segment.id,start:a,end:b,...description,
      mappingStatus:displayTargetText(participant,segment.mapping_status),
      thresholdStatus:displayTargetText(participant,segment.threshold_status)});
    }
    const sensingOnly = /sensing[ _-]*only/i.test(description.mode);
    const thresholdLines = (sensingOnly ? [] : segment.thresholds || []).filter(threshold=>finite(threshold.value))
      .map(threshold=>`${threshold.label || 'Configured threshold'}: ${threshold.value} LSB`);
    const detail = neuralHoverLines([...neuralSettingsLines(segment,panel.side,participant),
      `Mode: ${description.mode}`,`Adaptive state: ${segment.adaptive_state || 'Not recorded'}`,
      `Biomarker source: ${description.source}`,`Sensing contacts: ${description.contacts}`,description.center,description.band,
      `Control mapping: ${displayTargetText(participant,segment.mapping_status) || 'Not established'}`,...thresholdLines,
      ...(segment.threshold_status ? [displayTargetText(participant,segment.threshold_status)] : []),
      'Click for complete settings']);
    for (const metric of ['power','amplitude']) {
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
        const amplitude = finite(point.amplitude) && !point.amplitude_conflict ? `${point.amplitude} mA` : 'Not established';
        x.push(localTime(point.time)); y.push(value);
        customdata.push([segment.id,`${escapeText(localTime(point.time))} · Pacific<br>Biomarker: ${escapeText(power)}<br>Stimulation amplitude: ${escapeText(amplitude)}<br>${detail}`]);
        if (value !== null) {count++;latestTime = latestTime === null ? point.time : Math.max(latestTime,point.time);}
        previous = point.time;
      }
      if (metric === 'power') observedPower += count;
      else observedAmplitude += count;
      if (!count) continue;
      traces.push({type:'scatter',mode:'lines+markers',name:metric === 'power' ? `${description.source} biomarker` : `${neuralSourceLabel(panel.side,participant)} stimulation amplitude`,
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
