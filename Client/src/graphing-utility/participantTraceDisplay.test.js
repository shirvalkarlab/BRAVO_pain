/** @jest-environment node */
import {RCS08_PARTICIPANT_ID as id} from 'utils/participantTargets';
import {displayReportTrace, reportDisplayTraces, rawTraceName, isTargetDisplayReport} from './participantTraceDisplay';

test('only reviewed built-in neural report routes use presentation names', () => {
  ['therapy-history','nerual-activity-snapshot','time-series-analysis','chronic-neural-activity','multimodal-timeline-report'].forEach(report =>
    expect(isTargetDisplayReport(`/reports/${report}/${id}`)).toBe(true));
  ['', '/', `/analysis-builder/${id}`, `/reports/oura-freereps/${id}`,
    `/reports/time-series-analysis/other`, `/custom/time-series-analysis/${id}`, `/reports/time-series-analysis/${id}/child`].forEach(path =>
    expect(isTargetDisplayReport(path)).toBe(false));
  const traces=[{name:'Left GPi'}];
  expect(reportDisplayTraces(traces)).toBe(traces);
  expect(reportDisplayTraces(traces,`/analysis-builder/${id}`)).toBe(traces);
  global.window={location:{pathname:`/reports/time-series-analysis/${id}`}};
  expect(reportDisplayTraces(traces)[0].name).toBe('L GPe');
  delete global.window;
});

test('legend and hover changes preserve callback channel identity, arrays and raw export names', () => {
  const raw=Object.freeze({name:'Percept: Left GPi LFP',id:'Left GPi LFP',legendgroup:'Left GPi',
    current_alignment:42,x:[1,2],y:[0,4],customdata:[['Left GPi']],meta:{source:'native'},
    hovertemplate:'Left GPi %{y} · Right VIM %{x}',hovertext:['L 0-2',null],text:['R 9-10',5]});
  const shown=displayReportTrace(raw,id);
  expect(shown.name).toBe('Percept: L GPe LFP');
  expect(shown.hovertemplate).toBe('L GPe %{y} · R MD Thal %{x}');
  expect(shown.hovertext).toEqual(['L GPe 0-2',null]);
  expect(shown.text).toEqual(['R MD Thal 9-10',5]);
  expect(shown.id).toBe(raw.id);expect(shown.legendgroup).toBe(raw.legendgroup);
  for(const key of ['x','y','customdata']) expect(shown[key]).toBe(raw[key]);
  expect(shown.current_alignment).toBe(42);
  expect(shown.meta).toEqual({source:'native',bravoRawName:raw.name});
  // Plotly may copy the input object into click-event data. Raw identity is
  // serializable metadata, so alignment callbacks and raw export still resolve it.
  const clicked=JSON.parse(JSON.stringify(shown));
  expect(rawTraceName(clicked)).toBe(raw.name);
  expect(displayReportTrace(shown,id).meta.bravoRawName).toBe(raw.name);
  expect(raw.name).toBe('Percept: Left GPi LFP');expect(raw.meta).toEqual({source:'native'});
});

test('annotations, other participants and existing meta contracts remain unchanged', () => {
  const raw={name:'Left GPi'};
  expect(displayReportTrace(raw,'RCS09')).toBe(raw);
  const annotation={...raw,meta:{bravoPreserveLabel:true}};
  expect(displayReportTrace(annotation,id)).toBe(annotation);
  for(const meta of ['metadata',7,['Left GPi']]) {
    const source={...raw,meta};expect(displayReportTrace(source,id)).toBe(source);
  }
  const unrelated={name:'Mood',text:'score',hovertemplate:'%{y}'};
  expect(displayReportTrace(unrelated,id)).toBe(unrelated);
  expect(rawTraceName(raw)).toBe('Left GPi');
  expect(rawTraceName({name:'display',meta:{bravoRawName:''}})).toBe('');
  expect(displayReportTrace({hovertext:'Right VIM'},id).hovertext).toBe('R MD Thal');
});
