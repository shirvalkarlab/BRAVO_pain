import {render, screen, fireEvent, act, waitFor} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Biomarkers from './index';
import {SessionController} from 'database/session-control';
import {MODULES, cacheScope, getResult, invalidateAll, settingsKey} from 'database/resultCache';

jest.mock('react-router-dom', () => ({useNavigate: () => jest.fn(), useParams: () => ({participant_uid:'synthetic-metric-viewer'})}));
jest.mock('database/session-control', () => ({SessionController:{query:jest.fn(),getUser:jest.fn(),getSession:jest.fn(),getServer:jest.fn(),setSession:jest.fn(),displayError:jest.fn()}}));
jest.mock('layouts/DatabaseLayout', () => ({children}) => <div>{children}</div>);
jest.mock('./BiomarkerAnalytics', () => () => null);
jest.mock('./BiomarkerTimeline', () => () => null);
jest.mock('./BiomarkerDataTimeline', () => () => null);
jest.mock('./BinarizationPreview', () => () => null);
jest.mock('../ClosedLoopSim/PsdLsbPanel', () => () => null);
jest.mock('../ClosedLoopSim/ConversionModelPanel', () => () => null);
jest.mock('plotly.js-dist', () => ({react:jest.fn(),purge:jest.fn()}));

const uid = 'synthetic-metric-viewer';
const identity = {status:200,data:{boot_token:'synthetic-metric-qc1',stable_across_workers:true}};
const result = {available:true,label_metric:'vas',InputManifest:{revision:'synthetic-metric-qc1'}};
const analysisCalls = () => SessionController.query.mock.calls.filter(([url]) => url === '/api/queryBiomarkerAnalysis');
const settle = () => act(async () => {await Promise.resolve();await Promise.resolve();});
function View() {return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><Biomarkers/></PlatformContextProvider></ThemeProvider>;}
function transport(availability = {}) {
  SessionController.query.mockImplementation(url => Promise.resolve(
    url === '/api/queryServerIdentity' ? identity :
    url === '/api/queryDataAvailability' ? {status:200,data:availability} :
    url === '/api/queryBiomarkerAnalysis' ? {status:200,data:result} : {status:200,data:{}}));
}
beforeEach(() => {
  jest.clearAllMocks();localStorage.clear();
  SessionController.getUser.mockReturnValue({ID:'synthetic-viewer',Role:'User'});
  SessionController.getSession.mockReturnValue({ActiveStudy:'synthetic-study'});
  SessionController.getServer.mockReturnValue('synthetic-local');
  cacheScope();invalidateAll();transport();
});

const options = [{key:'nrs',label:'NRS (0–10)'},{key:'vas',label:'Overall VAS'}];
test.each([
  ['absent availability', {}],
  ['empty availability', {availability:{records:[]}}],
  ['normal availability', {availability:{records:[{channel:'synthetic-left',dtype:'timedomain'}]},available_metrics:options}],
])('metric selection remains available with %s and only explicit Start submits the selected metric', async (_state, availability) => {
  transport(availability);render(<View/>);await settle();
  expect(analysisCalls()).toHaveLength(0);
  const picker = screen.getByRole('button',{name:'NRS (0–10)'});
  fireEvent.mouseDown(picker);
  expect(screen.getByRole('option',{name:'NRS (0–10)'})).toBeTruthy();
  fireEvent.click(screen.getByRole('option',{name:'Overall VAS'}));
  expect(screen.getByRole('button',{name:'Overall VAS'})).toBeTruthy();
  await settle();expect(analysisCalls()).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:/Start exploratory analysis/}));
  await waitFor(() => expect(analysisCalls()).toHaveLength(1));
  const [url, body] = analysisCalls()[0];const {ParticipantId,...settings} = body;
  expect(url).toBe('/api/queryBiomarkerAnalysis');
  expect(body).toMatchObject({ParticipantId:uid,LabelMetric:'vas',LabelStrategy:'tertile',MatchToleranceMin:60});
  expect(SessionController.query).toHaveBeenCalledWith('/api/queryServerIdentity',{ParticipantId:uid});
  const identityIndex = SessionController.query.mock.calls.findIndex(([path]) => path === '/api/queryServerIdentity');
  const analysisIndex = SessionController.query.mock.calls.findIndex(([path]) => path === '/api/queryBiomarkerAnalysis');
  expect(identityIndex).toBeLessThan(analysisIndex);
  await waitFor(() => expect(getResult(MODULES.biomarkers,ParticipantId,settingsKey(settings))?.bundle).toEqual(result));
  expect(getResult(MODULES.biomarkers,ParticipantId,settingsKey({...settings,LabelMetric:'nrs'}))?.stale).toBe(true);
  expect(analysisCalls()).toHaveLength(1);
});

test('a viewer identity denial still prevents the selected analysis from starting or entering the cache', async () => {
  transport();const normalQuery = SessionController.query.getMockImplementation();
  const denied = {response:{status:403}};
  SessionController.query.mockImplementation((url,body) => url === '/api/queryServerIdentity' ? Promise.reject(denied) : normalQuery(url,body));
  render(<View/>);await settle();
  fireEvent.mouseDown(screen.getByRole('button',{name:'NRS (0–10)'}));
  fireEvent.click(screen.getByRole('option',{name:'Overall VAS'}));
  fireEvent.click(screen.getByRole('button',{name:/Start exploratory analysis/}));
  await waitFor(() => expect(SessionController.displayError).toHaveBeenCalled());
  expect(SessionController.query).toHaveBeenCalledWith('/api/queryServerIdentity',{ParticipantId:uid});
  expect(analysisCalls()).toHaveLength(0);
  expect(getResult(MODULES.biomarkers,uid,settingsKey({LabelMetric:'vas'}))).toBeNull();
});
