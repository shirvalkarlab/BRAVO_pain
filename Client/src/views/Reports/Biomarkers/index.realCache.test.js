import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Biomarkers from './index';
import StimOptimizer from '../StimOptimizer';
import {SessionController} from 'database/session-control';
import {MODULES,cacheScope,getResult,invalidateAll,settingsKey} from 'database/resultCache';

jest.mock('react-router-dom',()=>({useNavigate:()=>jest.fn(),useParams:()=>({participant_uid:'synthetic-live-hook'})}));
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn(),getUser:jest.fn(),getSession:jest.fn(),getServer:jest.fn(),setSession:jest.fn(),displayError:jest.fn()}}));
jest.mock('layouts/DatabaseLayout',()=>({children})=><div>{children}</div>);
jest.mock('./BiomarkerAnalytics',()=>()=>null);
jest.mock('./BiomarkerTimeline',()=>()=>null);
jest.mock('./BiomarkerDataTimeline',()=>()=>null);
jest.mock('./BinarizationPreview',()=>()=>null);
jest.mock('../ClosedLoopSim/PsdLsbPanel',()=>()=>null);
jest.mock('../ClosedLoopSim/ConversionModelPanel',()=>()=>null);
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
const user={ID:'synthetic-viewer',Role:'User'};
const identity={status:200,data:{boot_token:'synthetic-clean-v1',stable_across_workers:true}};
const payload={available:true,arms:{},InputManifest:{revision:'synthetic-clean-v1'}};
const scienceCalls=path=>SessionController.query.mock.calls.filter(([url])=>url===path);
function View({children}){return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}>{children}</PlatformContextProvider></ThemeProvider>;}
beforeEach(()=>{
  jest.clearAllMocks();localStorage.clear();
  SessionController.getUser.mockReturnValue(user);SessionController.getSession.mockReturnValue({ActiveStudy:'synthetic'});SessionController.getServer.mockReturnValue('test-local');
  cacheScope();invalidateAll();
  SessionController.query.mockImplementation(url=>Promise.resolve(url==='/api/queryServerIdentity'?identity:{status:200,data:payload}));
});
const settle=()=>act(async()=>{await Promise.resolve();await Promise.resolve();});

test('real cache hook keeps optimizer mount read-only, starts on click and caches only after 202 polling completes',async()=>{
  let n=0;
  SessionController.query.mockImplementation(url=>Promise.resolve(url==='/api/queryServerIdentity'?identity:
    url==='/api/queryStimOptimizer'?(++n===1?{status:202,headers:{'retry-after':'1'},data:{status:'running'}}:{status:200,data:payload}):{status:200,data:{}}));
  render(<View><StimOptimizer/></View>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Start analysis'})).toBeTruthy());await settle();
  expect(scienceCalls('/api/queryStimOptimizer')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button',{name:'Start analysis'}));
  await waitFor(()=>expect(scienceCalls('/api/queryStimOptimizer')).toHaveLength(1));
  const body=scienceCalls('/api/queryStimOptimizer')[0][1];const {ParticipantId,...settings}=body;
  expect(settings).toMatchObject({Sites:['left_leg','back'],Hemispheres:['Left','Right'],WashinMin:1,NBatches:3,Q:4});
  expect(getResult(MODULES.stimOptimizer,ParticipantId,settingsKey(settings))).toBeNull();
  await waitFor(()=>expect(getResult(MODULES.stimOptimizer,ParticipantId,settingsKey(settings))?.bundle).toEqual(payload),{timeout:3000});
  expect(scienceCalls('/api/queryStimOptimizer')).toHaveLength(2);
});

test.each([false,true])('real biomarker Compute uses committed current controls and runs once (saved controls: %s)',async(saved)=>{
  let releaseIdentity;const gate=new Promise(resolve=>{releaseIdentity=resolve;});
  if(!saved)SessionController.query.mockImplementation(url=>url==='/api/queryServerIdentity'?gate:Promise.resolve({status:200,data:payload}));
  if(saved)localStorage.setItem('bravo.biomarkerControls.synthetic-live-hook',JSON.stringify({schema:'biomarker_controls_v1',metric:'vas',matchTolerance:90,requestParams:{LabelMetric:'nrs',MatchToleranceMin:30}}));
  render(<View><Biomarkers/></View>);await settle();
  expect(scienceCalls('/api/queryBiomarkerAnalysis')).toHaveLength(0);
  await waitFor(()=>expect(screen.getByRole('button',{name:/Start exploratory analysis/}).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:/Start exploratory analysis/}));
  if(!saved){await settle();expect(scienceCalls('/api/queryBiomarkerAnalysis')).toHaveLength(0);await act(async()=>releaseIdentity(identity));}
  await waitFor(()=>expect(scienceCalls('/api/queryBiomarkerAnalysis')).toHaveLength(1));
  const body=scienceCalls('/api/queryBiomarkerAnalysis')[0][1];const {ParticipantId,...settings}=body;
  expect(body).toMatchObject({ParticipantId:'synthetic-live-hook',LabelMetric:saved?'vas':'nrs',MatchToleranceMin:saved?90:60,LabelStrategy:'tertile'});
  await waitFor(()=>expect(getResult(MODULES.biomarkers,ParticipantId,settingsKey(settings))?.bundle).toEqual(payload));
  expect(scienceCalls('/api/queryBiomarkerAnalysis')).toHaveLength(1);
});
