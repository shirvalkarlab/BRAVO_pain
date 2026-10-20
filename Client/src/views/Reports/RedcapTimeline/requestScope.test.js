/** @jest-environment node */
import {cacheScope} from './requestScope';
import {SessionController} from 'database/session-control';
jest.mock('database/session-control',()=>({SessionController:{getUser:jest.fn(),getSession:jest.fn(),getServer:jest.fn()}}));
beforeEach(()=>{SessionController.getUser.mockReturnValue({id:'synthetic-user'});SessionController.getSession.mockReturnValue({ActiveStudy:'study-a'});SessionController.getServer.mockReturnValue('http://test.invalid');});
test('logout and absent account cannot start scoped requests',()=>{
 for(const user of [null,undefined,{},'invalid']){SessionController.getUser.mockReturnValue(user);expect(cacheScope()).toBeNull();}
});
test('scope is stable for unchanged identity and ignores unrelated navigation',()=>{
 const original=cacheScope();SessionController.getSession.mockReturnValue({page:4,ActiveStudy:'study-a'});expect(cacheScope()).toBe(original);
});
test('account replacement, study, permission and server changes reject stale responses',()=>{
 let prior=cacheScope();
 for(const change of [()=>SessionController.getUser.mockReturnValue({id:'synthetic-user'}),()=>SessionController.getSession.mockReturnValue({ActiveStudy:'study-b'}),()=>SessionController.getSession.mockReturnValue({ActiveStudy:'study-b',Access:['read']}),()=>SessionController.getServer.mockReturnValue('http://second.invalid')]){
 change();const next=cacheScope();expect(next).not.toBe(prior);prior=next;
 }
});
test('property ordering does not change a session scope and missing session is supported',()=>{
 SessionController.getSession.mockReturnValue({Access:['read'],ActiveStudy:'a'});const first=cacheScope();SessionController.getSession.mockReturnValue({ActiveStudy:'a',Access:['read']});expect(cacheScope()).toBe(first);
 SessionController.getSession.mockReturnValue(null);expect(typeof cacheScope()).toBe('string');
});
