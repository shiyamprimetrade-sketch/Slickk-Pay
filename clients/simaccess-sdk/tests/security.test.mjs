import test from 'node:test';
import assert from 'node:assert/strict';
import {
  LocalTransport,guardedGetRetry,neverRetryMutation,makeFetchAdapter,
  InMemorySession,parseSessionCreated,SessionSnapshotCache,OfflinePolicy,
  RecoveryDesk,decideRecovery,ConnectionCircuit,SafeModeController,
  DeviceSafetyController,AndroidLabAdapter,TelemetryDesk,RefreshCoordinator,
  inspectOutgoing,assertNoFinancialPermission,decideRoleAction,
  ensureLocalDescriptor,safeRelativeRoute,safeQuery,parseJson,
  noCredentialFields,privacyLintTelemetry,SessionSnapshotCache as Cache
} from '../dist/index.js';
const actor='sim_customer_alpha',device='sim_device_customer_alpha_004';
const now=1800000000,clock={nowSeconds:()=>now,trustedClock:true};
test('local-only URL allowlist denies external origins and embedded credentials',()=>{
 assert.equal(ensureLocalDescriptor('http://127.0.0.1:8011'),'http://127.0.0.1:8011');
 for(const host of ['https://payments.example.com','http://192.168.0.1:8000',
  'https://user:password@localhost','http://localhost.evil.tld',
  'http://127.0.0.1:8000/other'])assert.throws(()=>ensureLocalDescriptor(host));
 assert.equal(safeRelativeRoute('/lab/v4/activity/search?limit=20'),'/lab/v4/activity/search?limit=20');
 for(const route of ['/api/pay','/lab/v4/../post','/lab/v4/x#fragment','/lab/v4/a//b'])
  assert.throws(()=>safeRelativeRoute(route));
});
test('query serializer validates keys and values',()=>{
 assert.equal(safeQuery({limit:10}),'?limit=10');
 assert.throws(()=>safeQuery({'a/b':10}));
 assert.throws(()=>safeQuery({id:'bad\nvalue'}));
});
test('opaque sessions are in memory and cannot be reused after lock',()=>{
 const store=new InMemorySession(clock);
 const payload={actor,role:'customer',expiresAt:now+100,bearer:'X'.repeat(60)};
 store.attach(payload,device);
 assert.equal(store.status(),'active');
 const headers=store.withTransientHeaders(x=>x);
 assert.ok(headers.Authorization.startsWith('Bearer '));
 assert.equal(store.debug().hasBearer,true);
 store.beforeBackground();
 assert.equal(store.status(),'locked');
 assert.throws(()=>store.withTransientHeaders(()=>null));
 assert.equal(store.debug().hasBearer,false);
});
test('invalid session tokens and live claims are rejected',()=>{
 assert.throws(()=>parseSessionCreated({token:'short',actor,role:'customer',expires_at:now+100,simulation:true,real_money:false}));
 assert.throws(()=>parseSessionCreated({token:'X'.repeat(60),actor,role:'customer',expires_at:now+100,simulation:true,real_money:true}));
});
test('cache isolates actors and never authorizes offline balances',()=>{
 const cache=new Cache(()=>1000);
 cache.bindActor(actor);
 cache.save('quotes',{simulation:true,count:1},3000);
 assert.equal(cache.read('quotes').state,'fresh');
 cache.bindActor('sim_customer_beta');
 assert.equal(cache.read('quotes').state,'missing');
 assert.throws(()=>cache.save('private',{passwd:'do not store this'},3000));
 assert.equal(cache.mayAuthorizeOffline(),false);
});
test('offline state forbids queued financial mutations',()=>{
 const offline=new OfflinePolicy(()=>1000);
 offline.transition({type:'connected',at:1000});
 assert.equal(offline.mayRefresh(),true);
 offline.transition({type:'disconnected',at:1001});
 assert.equal(offline.mayQueueFinancialOperation(),false);
 assert.throws(()=>offline.requireOnline());
});
test('recovery never retries uncertain preview POSTs',()=>{
 const a={route:'/lab/v4/quotes',kind:'preview_mutation',attemptId:'preview_retry_0001',outcome:'timeout',timestamp:123,simulation:true};
 assert.equal(decideRecovery(a).decision,'inspect_server');
 const desk=new RecoveryDesk(()=>125);
 desk.observe(a);
 assert.equal(desk.unresolved().length,1);
 desk.resolve(a.attemptId,'quoted');
 assert.equal(desk.unresolved().length,0);
 assert.equal(decideRecovery({...a,kind:'money_mutation'}).decision,'stop');
});
test('circuit breaker blocks recurrent failed reads',()=>{
 let at=0;const circuit=new ConnectionCircuit(()=>at,2,1000);
 assert.equal(circuit.maySendRead(),true);
 circuit.failure();circuit.failure();
 assert.equal(circuit.maySendRead(),false);
 at=1001;assert.equal(circuit.maySendRead(),true);
 circuit.success();assert.equal(circuit.snapshot().state,'closed');
 assert.equal(circuit.mayRetryPost(),false);
});
test('client policy blocks every financial action',()=>{
 assertNoFinancialPermission();
 for(const role of ['customer','agent','merchant','operator']){
  assert.equal(decideRoleAction(role,'money:post').allow,false);
  assert.equal(decideRoleAction(role,'loan:disburse').allow,false);
 }
 assert.equal(inspectOutgoing({method:'POST',path:'/lab/v4/ledger/post',headers:{}}).accepted,false);
});
test('privacy and telemetry omit secrets',()=>{
 assert.throws(()=>noCredentialFields({password:'abc'}));
 assert.equal(privacyLintTelemetry('Authorization: Bearer abc'),false);
 const telemetry=new TelemetryDesk(()=>1000);
 telemetry.append('network_request','success',300);
 assert.equal(telemetry.summary().p95LatencyMs,300);
 assert.equal(telemetry.mayLogBearerTokens(),false);
});
test('local transport enforces response labels, no redirects and no external origin',async()=>{
 const adapter={send:async(url,req)=>({url,status:200,body:JSON.stringify({simulation:true,count:3}),contentType:'application/json',redirected:false})};
 const transport=new LocalTransport('http://localhost:8000',adapter);
 assert.equal((await transport.call({method:'GET',path:'/lab/v4/health',headers:{}})).count,3);
 const hostile=new LocalTransport('http://localhost:8000',{send:async()=>({status:200,url:'https://evil.invalid/lab/v4/health',body:'{"simulation":true}',contentType:'application/json',redirected:true})});
 await assert.rejects(()=>hostile.call({method:'GET',path:'/lab/v4/health',headers:{}}));
});
test('safe-mode invalidates sessions and caches',()=>{
 const session=new InMemorySession(clock),cache=new Cache(()=>1000),offline=new OfflinePolicy(()=>1000);
 session.attach({actor,role:'customer',expiresAt:now+100,bearer:'X'.repeat(60)},device);
 cache.bindActor(actor);cache.save('agents',{simulation:true},1000);
 const controller=new SafeModeController(session,cache,offline,()=>1000);
 controller.enter('contract_mismatch');
 assert.equal(cache.size(),0);assert.equal(session.debug().hasBearer,false);
 assert.equal(controller.state().active,true);
});
test('device background event blocks local private views',()=>{
 const session=new InMemorySession(clock),cache=new Cache(()=>1000),offline=new OfflinePolicy(()=>1000);
 session.attach({actor,role:'customer',expiresAt:now+100,bearer:'X'.repeat(60)},device);
 const guard=new DeviceSafetyController(device,session,cache,offline);
 guard.setScreenProtected(true);guard.handle('foreground');guard.unlockSyntheticView();
 assert.equal(guard.isSensitiveViewAllowed(),true);
 const bridge=new AndroidLabAdapter(guard,offline,cache);
 bridge.onAndroidEvent({type:'app_state',value:'background',at:1000});
 assert.equal(guard.isSensitiveViewAllowed(),false);
 assert.equal(bridge.snapshot().financialPostsQueued,0);
});
