import {screen, fireEvent} from '@testing-library/react';
import {act} from 'react-dom/test-utils';
import {createRoot} from 'react-dom/client';
import {StrictMode} from 'react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Plotly from 'plotly.js-dist';
import BiomarkerTimeline from './BiomarkerTimeline';
import Biomarkers from './index';

let mockParticipant = 'synthetic-a';
let mockResult;
const mockQuery = jest.fn();
jest.mock('react-router-dom', () => ({useNavigate: () => jest.fn(), useParams: () => ({participant_uid: mockParticipant})}));
jest.mock('./queryAnalysis', () => ({useAnalysisQuery: () => mockQuery}));
jest.mock('database/useCachedResult', () => ({useCachedResult: () => ({data: mockResult, staleReasons: [], recompute: jest.fn()})}));
jest.mock('layouts/DatabaseLayout', () => ({children}) => <div>{children}</div>);
jest.mock('./BiomarkerAnalytics', () => () => null);
jest.mock('./BiomarkerDataTimeline', () => () => null);
jest.mock('./BinarizationPreview', () => () => null);
jest.mock('../ClosedLoopSim/PsdLsbPanel', () => () => null);
jest.mock('../ClosedLoopSim/ConversionModelPanel', () => () => null);
jest.mock('plotly.js-dist', () => ({react: jest.fn(), purge: jest.fn(), relayout: jest.fn()}));

function View({children}) {
  return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}>{children}</PlatformContextProvider></ThemeProvider>;
}
const fixture = (offset = 0) => ({timeline: [
  {time: 1700000000, td_biomarker_value: 2 + offset, nrs: 1, td_stim_amplitude: 1.5},
  {time: 1700000060, td_biomarker_value: null, nrs: 4, td_stim_amplitude: null},
  {time: 1700000120, td_biomarker_value: 6 + offset, nrs: 7, td_stim_amplitude: 2},
]});
const lastPlot = () => Plotly.react.mock.calls.at(-1);
// Match the application's React 18 mount, including passive-effect cleanup semantics.
const mounted = new Set();
function render(ui) {
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  const view = {
    // Native createRoot.render (not a Testing Library utility) needs an act boundary.
    // eslint-disable-next-line testing-library/no-unnecessary-act
    rerender: next => act(() => root.render(next)),
    unmount: () => {act(() => root.unmount()); container.remove(); mounted.delete(view);},
  };
  mounted.add(view); view.rerender(ui); return view;
}
beforeAll(() => {global.IS_REACT_ACT_ENVIRONMENT = true;});
afterEach(() => {for (const view of mounted) view.unmount();});
afterAll(() => {delete global.IS_REACT_ACT_ENVIRONMENT;});

beforeEach(() => {
  jest.clearAllMocks(); localStorage.clear(); mockParticipant = 'synthetic-a'; mockResult = null;
  mockQuery.mockResolvedValue({status:200, data:{}}); mockQuery.cancel = jest.fn();
  // Model the public Plotly contract: react retains state for a stable uirevision;
  // purge destroys it. An EventEmitter checks handler identity and foreign ownership.
  Plotly.react.mockImplementation((gd, traces, layout) => {
    if (!gd.on) {
      const {EventEmitter} = require('events');
      const emitter = new EventEmitter();
      gd.on = emitter.on.bind(emitter); gd.removeListener = jest.fn(emitter.removeListener.bind(emitter));
      gd.emit = emitter.emit.bind(emitter); gd.listeners = emitter.listeners.bind(emitter);
    }
    if (gd.plot?.revision !== layout.uirevision) gd.plot = {revision: layout.uirevision};
    gd.plot.traces = traces;
  });
  Plotly.purge.mockImplementation(gd => {delete gd.plot;});
  Plotly.relayout.mockResolvedValue(undefined);
});

test('data, height and link updates patch the same plot without destroying its zoom or other listeners', () => {
  const data = fixture(); const before = JSON.stringify(data);
  const view = render(<View><BiomarkerTimeline data={data}/></View>);
  const [gd,,layout] = lastPlot(); const foreign = jest.fn(); gd.on('plotly_relayout', foreign);
  const originalHandler = gd.listeners('plotly_relayout')[0]; gd.plot.zoom = [1, 2];
  view.rerender(<View><BiomarkerTimeline data={fixture(10)} height={700}/></View>);
  expect(lastPlot()[0]).toBe(gd); expect(lastPlot()[2].height).toBe(700);
  expect(lastPlot()[2].uirevision).toBe(layout.uirevision); expect(layout.uirevision).toBeTruthy();
  expect(gd.plot.zoom).toEqual([1, 2]); expect(Plotly.purge).not.toHaveBeenCalled();
  expect(gd.removeListener).toHaveBeenCalledWith('plotly_relayout', originalHandler);
  expect(gd.listeners('plotly_relayout')).toHaveLength(2);
  expect(gd.listeners('plotly_relayout')).toContain(foreign);
  expect(gd.plot.traces[0].y).toEqual([12, null, 16]);
  fireEvent.click(screen.getByRole('checkbox'));
  expect(lastPlot()[2].xaxis3.matches).toBeUndefined();
  expect(Plotly.purge).not.toHaveBeenCalled(); expect(gd.plot.zoom).toEqual([1, 2]);
  expect(gd.listeners('plotly_relayout')).toHaveLength(2);
  fireEvent.click(screen.getByRole('checkbox'));
  expect(lastPlot()[2].xaxis3.matches).toBe('x');
  expect(JSON.stringify(data)).toBe(before);
});

test.each([null, {}, {timeline: []}, {timeline: 'invalid'}, {timeline: [null]},
  {timeline: [5]}, {timeline: [[]]}, {timeline: [{time: 1700000000, unknown: 2}]}])(
  'clears an existing plot and owned listener when the result is empty/invalid (%j)', data => {
    const view = render(<View><BiomarkerTimeline data={fixture()}/></View>);
    const [gd] = lastPlot(); const owned = gd.listeners('plotly_relayout')[0];
    view.rerender(<View><BiomarkerTimeline data={data}/></View>);
    expect(Plotly.purge).toHaveBeenCalledWith(gd); expect(gd.plot).toBeUndefined();
    expect(gd.removeListener).toHaveBeenCalledWith('plotly_relayout', owned);
    expect(Plotly.react).toHaveBeenCalledTimes(1);
    view.rerender(<View><BiomarkerTimeline data={fixture(20)}/></View>);
    expect(gd.plot.traces[0].y).toEqual([22, null, 26]);
    expect(gd.listeners('plotly_relayout')).toHaveLength(1);
  }
);

test('purges the captured DOM node on true unmount, after React has detached it', () => {
  const view = render(<View><BiomarkerTimeline data={fixture()}/></View>);
  const [gd] = lastPlot(); const owned = gd.listeners('plotly_relayout')[0];
  Plotly.purge.mockImplementation(node => {
    expect(node).toBe(gd); expect(node.isConnected).toBe(false); delete node.plot;
  });
  view.unmount();
  expect(Plotly.purge).toHaveBeenCalledTimes(1);
  expect(gd.removeListener).toHaveBeenCalledWith('plotly_relayout', owned);
});

test('preserves raw values, epoch seconds, missing gaps, units, and linked zoom rescaling', async () => {
  const data = fixture();
  data.power_channels = [{channel:'L 0-3', hemisphere:'Left', around_the_clock:true,
    time:[1700000000,1700025200], band_power:[10,30], threshold:20}];
  render(<View><BiomarkerTimeline data={data}/></View>);
  const [gd,traces,layout] = lastPlot();
  expect(traces[0].x.map(Number)).toEqual([1700000000000,1700000060000,1700000120000]);
  expect(traces[0].y).toEqual([2,null,6]); expect(traces.every(t => t.connectgaps === false)).toBe(true);
  const chronic = traces.find(t => t.name === 'Chronic LFP power');
  expect(chronic.y).toEqual([10,null,30]); expect(chronic.x.map(Number)).toEqual([1700000000000,1700012600000,1700025200000]);
  expect(chronic.mode).toBe('lines');
  expect(layout.yaxis.title.text).toBe('mA'); expect(layout.yaxis4.title.text).toBe('PSD power');
  expect(layout.shapes.some(s => s.type === 'line' && s.y0 === 20 && s.y1 === 20)).toBe(true);
  await act(async () => gd.emit('plotly_relayout', {'xaxis.range[0]':'2023-11-14T22:13:20Z','xaxis.range[1]':'2023-11-14T22:15:20Z'}));
  expect(Plotly.relayout).toHaveBeenCalledWith(gd, expect.objectContaining({'yaxis4.range[0]': expect.any(Number)}));
  expect(gd.__rescaling).toBe(false);
});

test('the actual participant page remounts the timeline so another participant cannot inherit zoom or link state', async () => {
  mockResult = fixture();
  const view = render(<View><Biomarkers/></View>);
  await act(async () => {await Promise.resolve();});
  const [first] = lastPlot(); first.plot.zoom = [1,2];
  fireEvent.click(screen.getByRole('checkbox', {name:/LINK AXES/}));
  mockParticipant = 'synthetic-b'; mockResult = fixture(100);
  view.rerender(<View><Biomarkers/></View>);
  await act(async () => {await Promise.resolve();});
  const [second] = lastPlot();
  expect(second).not.toBe(first); expect(Plotly.purge).toHaveBeenCalledWith(first);
  expect(second.plot.zoom).toBeUndefined(); expect(second.plot.traces[0].y).toEqual([102,null,106]);
  expect(screen.getByRole('checkbox', {name:/LINK AXES/}).checked).toBe(true);
  expect(mockQuery.mock.calls.some(([url]) => url === '/api/queryBiomarkerAnalysis')).toBe(false);
});


test('React 18 strict effect replay restores the plot and keeps a single owned listener', () => {
  const view = render(<StrictMode><View><BiomarkerTimeline data={fixture()}/></View></StrictMode>);
  const [gd] = lastPlot();
  expect(gd.plot.traces[0].y).toEqual([2,null,6]);
  expect(gd.listeners('plotly_relayout')).toHaveLength(1);
  expect(Plotly.purge).toHaveBeenCalledTimes(1);
  view.unmount(); expect(Plotly.purge).toHaveBeenCalledTimes(2);
  expect(gd.listeners('plotly_relayout')).toHaveLength(0);
});
