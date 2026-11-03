import test from 'node:test';import assert from 'node:assert/strict';
import {MobileLabController} from '../dist/core/controller.js';
import {startDemoSession,updateSession,lockSession,authorizeFinancialAction,offlineActionPolicy,safeStoragePolicy} from '../dist/core/security.js';
import {sampleSnapshot} from '../dist/core/fixtures.js';
import {LocalNavigator} from '../dist/core/navigation.js';
import {OfflineWorkspace,backoffSchedule,planRefresh} from '../dist/core/offline.js';
import {ReadOnlyRecovery,recoveryPlan,permittedRetries} from '../dist/core/reliability.js';
import {newHandoverPreview,quoteHandover,startHandoverReview,acknowledgeCustomerDemo,acknowledgeAgentDemo} from '../dist/core/agentflow.js';
import {calculatePilotQuote} from '../dist/core/money.js';
import {assessDraftRisks} from '../dist/core/risk.js';
import {FixtureMobileSource,buildReadContext,assertSafeHandshake,rejectMobilePosting} from '../dist/core/protocol.js';
import {createDraft} from '../dist/core/drafts.js';
const at='2026-11-03T12:00:00Z', clock=Date.parse(at);
test('locked session prevents private fixture access',()=>{
 const s=startDemoSession('customer','sim_cust_0001',clock);
 assert.equal(updateSession(s,clock+60_000).locked,false);
 assert.equal(updateSession(s,clock+6*60_000).locked,true);
 assert.equal(lockSession(s).locked,true);
});
test('no financial action can be approved locally',()=>{
 const s=startDemoSession('customer','sim_cust_0001',clock);
 const draft=createDraft({ownerId:'sim_cust_0001',operation:'transfer',recipientId:'sim_cust_0002',amountText:'50.00'},at);
 const device={appForeground:true,screenProtected:true,hasTrustedLocalClock:true,network:'online',securityNoticeAcknowledged:true};
 assert.equal(authorizeFinancialAction(s,device,draft).enabled,false);
 assert.equal(offlineActionPolicy('online').confirmTransfer.enabled,false);
 assert.equal(offlineActionPolicy('offline').agentCashHandover.enabled,false);
});
test('sensitive balances and credentials never persist in preferences',()=>{
 for(const key of ['api_key','balance','pin','token','transaction'])assert.equal(safeStoragePolicy(key).persist,false);
 assert.equal(safeStoragePolicy('locale').persist,true);
});
test('role-aware navigation cannot elevate privileges',()=>{
 const nav=new LocalNavigator('customer');
 assert.throws(()=>nav.push('agent_dashboard'));
 nav.push('activity');assert.equal(nav.current().name,'activity');nav.back();assert.equal(nav.current().name,'home');
 assert.throws(()=>nav.resolveLink('slickkpaylab://transfer_quote'));
});
test('offline workspace does not queue payments',()=>{
 const workspace=new OfflineWorkspace();
 const draft=createDraft({ownerId:'sim_cust_0001',operation:'transfer',recipientId:'sim_cust_0002',amountText:'20.00'},at);
 assert.throws(()=>workspace.attemptFinancialQueue(draft));
 assert.equal(workspace.snapshot(at).paymentQueueLength,0);
 workspace.record('screen_view',{screen:'home'},at);
 assert.equal(workspace.snapshot(at).events.length,1);
 assert.throws(()=>workspace.record('screen_view',{token:'private'},at));
});
test('read-only retry policy uses bounded backoff',()=>{
 assert.equal(backoffSchedule(0),500);assert.equal(backoffSchedule(10)>=30000,true);
 const state={lastAttemptAt:at,lastSuccessAt:null,network:'online',serverVerified:false,stale:true,source:'sandbox_server'};
 assert.equal(planRefresh(state,'2026-11-03T12:00:01Z',true).attempt,false);
 assert.equal(planRefresh(state,'2026-11-03T12:00:11Z',true).attempt,true);
});
test('recovery never replays financial commands during network partition',()=>{
 const rec=new ReadOnlyRecovery();rec.acceptFixture(sampleSnapshot(),clock);
 rec.setNetwork('offline');rec.inject('network_partition',clock);
 assert.equal(rec.snapshot().canReplayPayments,false);
 assert.equal(recoveryPlan(rec.snapshot(),clock).retryRead,false);
 assert.throws(()=>rec.attemptWrite());
 assert.equal(permittedRetries().find(x=>x.action==='retry_transfer_post').allowed,false);
});
test('agent local acknowledgments do not verify real cash handover',()=>{
 const agent=sampleSnapshot().agents[0];
 const start=newHandoverPreview('sim_cust_0001',agent,'cash_out',10000,at);
 const reviewed=startHandoverReview(quoteHandover(start,at),true,at);
 const customer=acknowledgeCustomerDemo(reviewed,'sim_cust_0001',at);
 const ending=acknowledgeAgentDemo(customer,agent.id,at);
 assert.equal(ending.step,'unresolved');assert.equal(ending.financialPostingComplete,false);
 assert.equal(ending.physicalHandoverVerified,false);
 assert.throws(()=>acknowledgeCustomerDemo(reviewed,agent.id,at));
});
test('risk hints are advisory and cannot approve payment',()=>{
 const draft=createDraft({ownerId:'sim_cust_0001',operation:'cash_out',agentId:'sim_agent_0001',amountText:'100.00'},at);
 const snap=sampleSnapshot();const account=snap.accounts[0];
 const result=assessDraftRisks(draft,{actorId:snap.actor.id,account,network:'offline',agent:snap.agents[0],history:snap.transactions,now:at});
 assert.equal(result.blocksLocalSubmission,true);assert.equal(result.requiresServer,true);
});
test('mobile data source requires explicit fixture contracts',async()=>{
 const source=new FixtureMobileSource(persona=>sampleSnapshot(persona,'en'));
 const context=buildReadContext('sim_cust_0001','customer','offline','sim_request_00001');
 const handshake=await source.handshake(context);assertSafeHandshake(handshake);
 assert.equal(handshake.financialPostingEnabled,false);
 const data=await source.snapshot(context);assert.equal(data.actor.id,'sim_cust_0001');
 assert.throws(()=>rejectMobilePosting(null));
});
test('controller wipes synthetic drafts when switching persona',()=>{
 const c=new MobileLabController(Date.now());
 const draft=c.newDraft({operation:'transfer',recipientId:'sim_cust_0002',amountText:'50.00'});
 assert.equal(c.drafts().length,1);
 c.dispatch({kind:'persona',persona:'agent'});
 assert.equal(c.drafts().length,0);
 assert.equal(c.state().snapshot.actor.role,'agent');
 assert.throws(()=>c.receiptFromDraftId(draft.id));
 assert.throws(()=>c.cannotSendMoney());
});
