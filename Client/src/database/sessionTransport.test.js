import axios from 'axios';
import {SessionController} from './session-control';
jest.mock('axios',()=>({post:jest.fn()}));
jest.mock('components/MuiAlertDialog',()=>()=>null);

beforeEach(()=>{axios.post.mockReset();SessionController.setServer('');jest.useFakeTimers();});
afterEach(()=>jest.useRealTimers());
const network=()=>Object.assign(new Error('Network Error'),{code:'ERR_NETWORK'});

test('the actual query wrapper preserves body, headers and transport options for one network retry',async()=>{
 const body=Object.freeze({ParticipantId:'synthetic',Candidates:[],PainScore:'nrs'});
 const answer={data:{available:true}};
 axios.post.mockRejectedValueOnce(network()).mockResolvedValueOnce(answer);
 const result=SessionController.query('/api/queryClosedLoopDeployment',body,{'X-Test':'synthetic'},42000,'json');
 for(let i=0;i<5;i+=1) await Promise.resolve();
 expect(jest.getTimerCount()).toBe(1);jest.advanceTimersByTime(1500);
 await expect(result).resolves.toBe(answer);
 expect(axios.post).toHaveBeenCalledTimes(2);
 expect(axios.post.mock.calls[1]).toEqual(axios.post.mock.calls[0]);
 expect(axios.post.mock.calls[1]).toEqual(['/api/queryClosedLoopDeployment',body,{timeout:42000,responseType:'json',headers:{'X-Test':'synthetic','X-CSRFToken':''}}]);
});

test.each(['choose','clear'])('the actual query wrapper never replays chosen-band %s',async(Action)=>{
 const error=Object.assign(new Error('bad gateway'),{response:{status:502}});
 axios.post.mockRejectedValue(error);
 await expect(SessionController.query('/api/queryClosedLoopChosenBand',{ParticipantId:'synthetic',Action})).rejects.toBe(error);
 jest.advanceTimersByTime(3000);expect(axios.post).toHaveBeenCalledTimes(1);
});

test('a server-picker change during backoff cannot redirect the existing read to another host',async()=>{
 SessionController.setServer('https://original.test');
 axios.post.mockRejectedValueOnce(network()).mockResolvedValue({data:'original read'});
 const result=SessionController.query('/api/queryRedcapTimeline',{ParticipantId:'synthetic'});
 for(let i=0;i<5;i+=1) await Promise.resolve();
 SessionController.setServer('https://replacement.test');jest.advanceTimersByTime(1500);
 await expect(result).resolves.toEqual({data:'original read'});
 expect(axios.post.mock.calls.map(([url])=>url)).toEqual([
  'https://original.test/api/queryRedcapTimeline','https://original.test/api/queryRedcapTimeline']);
});
