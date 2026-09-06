import {render, screen} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Plotly from 'plotly.js-dist';
import BiomarkerDataTimeline from './BiomarkerDataTimeline';

let mockWidth = 390;
jest.mock('react-resize-detector', () => ({useResizeDetector: () => ({ref: require('react').useRef(null), width: mockWidth})}));
jest.mock('plotly.js-dist', () => ({
  react: jest.fn((gd) => {gd.on = jest.fn(); gd.removeListener = jest.fn();}),
  purge: jest.fn(), relayout: jest.fn(), restyle: jest.fn(),
}));
const fixture = () => ({participant_label:'Example', availability: {
  span:[100000,200000], records:[
    {channel:'ZERO_THREE_LEFT', label:'L 0-3', hemisphere:'LEFT',region:'GPe', dtype:'timedomain', t_start:100000,dur_s:30},
    {channel:'ONE_THREE_RIGHT',label:'R 1-3', hemisphere:'RIGHT',region:'MD Thal',dtype:'timedomain',t_start:150000,dur_s:60},
  ], pain:{metric:'NRS',t:[100000,200000],y:[1,8]}, stim:{t:[100000,200000],y:[2,3]},
}});
function View(props) {return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><BiomarkerDataTimeline {...props}/></PlatformContextProvider></ThemeProvider>;}
beforeEach(() => {jest.clearAllMocks(); mockWidth=390; Plotly.react.mockImplementation((gd) => {gd.on = jest.fn(); gd.removeListener = jest.fn();});});

test('keeps the complete scientific key outside the narrow plot and preserves samples and labels', () => {
  const data=fixture(); const before=JSON.stringify(data);
  const view = render(<View data={data}/>);
  const [,traces,layout] = Plotly.react.mock.calls.at(-1);
  expect(screen.getByRole('list',{name:'Timeline symbols'}).children).toHaveLength(7);
  expect(screen.getByText(/modeled LSB.*352.62/)).toBeTruthy();
  expect(layout.showlegend).toBe(false);
  expect(layout.margin.l).toBe(126);
  expect(layout.margin.r).toBe(12);
  expect(layout.xaxis.nticks).toBe(3);
  expect(layout.annotations.some((a)=>a.text.includes('GPe<br>'))).toBe(true);
  expect(traces.find((t)=>t.customdata?.[0]?.[0]===1).customdata.map((d)=>d[0])).toEqual([1,8]);
  expect(JSON.stringify(data)).toBe(before);
  expect(screen.queryByText(/Scroll horizontally/)).toBeNull();
  expect(screen.getByRole('region',{name:'Biomarker data timeline'}).firstChild.style.minWidth).toBe('0');
  view.unmount(); expect(Plotly.purge).toHaveBeenCalled();
});

test('redraws at desktop width with full original region labels and denser time ticks', () => {
  const data=fixture(); const view=render(<View data={data}/>);
  mockWidth=1200; view.rerender(<View data={data}/>);
  const layout=Plotly.react.mock.calls.at(-1)[2];
  expect(layout.xaxis.nticks).toBe(8);
  expect(layout.margin.l).toBeGreaterThan(126);
  expect(layout.annotations.filter((a)=>a.textangle===-90)).toHaveLength(2);
  expect(layout.font.family).toBe('Roboto, sans-serif');
});

test('no data remains explicit', () => {
  render(<View data={{}}/>);
  expect(screen.getByText(/No availability data/)).toBeTruthy();
  expect(Plotly.react).not.toHaveBeenCalled();
});

test('unassessed matching has cross symbols and explicit local legend rather than falsely reporting failed matches',()=>{
  const data=fixture(),scanModel={matchable:false,binByKey:new Map(),matchedValues:[],painMatched:[],cuts:{kind:'none'}};
  render(<View data={data} scanModel={scanModel} colorMode="binarization" setColorMode={()=>{}}/>);
  const [,traces]=Plotly.react.mock.calls.at(-1);
  const pain=traces.find(t=>t.customdata?.[0]?.[0]===1);
  expect(pain.marker.symbol).toEqual(['x-thin','x-thin']);expect(pain.customdata.map(d=>d[1])).toEqual(['match not assessed','match not assessed']);
  expect(screen.getByRole('list',{name:'Timeline symbols'}).textContent).toContain('match not assessed');
  expect(screen.getByRole('list',{name:'Timeline symbols'}).textContent).toContain('×');
});
