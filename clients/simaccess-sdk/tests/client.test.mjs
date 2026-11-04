import test from 'node:test';
import assert from 'node:assert/strict';
import {createLabRuntime,poisha,LabClientError,
  startLocalDemo,stopLocalDemo,parseQuote,checkFinancialSafety,
  safeQuery,SessionSnapshotCache,neverRetryMutation} from '../dist/index.js';
const actor='sim_customer_alpha',device='sim_device_customer_alpha_004';
const qid='sim_quote_00001';
const base='http://127.0.0.1:8011';
function createCannedAdapter({wrongOwner=false,unsafe=false,failPost=false}={}){
 const history=[];
 const quote={quote_id:qid,owner_id:wrongOwner?'sim_other_user':actor,
  operation:'transfer',counterpart_id:'sim_customer_beta',principal_poisha:10000,
  fee_poisha:0,total_poisha:10000,version:'pilot-001',status:'quoted',
  expires_at:1800000000,simulation:true,can_execute:false,real_money:false,tax_unverified:true};
 return {history,adapter:{send:async(url,request)=>{
  history.push({url,method:request.method,path:request.path,headers:request.headers,body:request.body});
  const pathname=new URL(url).pathname;
  let result;
  if(pathname==='/lab/v4/health')result={simulation:true,healthy:true,real_money:false};
  else if(pathname==='/lab/v4/capabilities')result={simulation:true,bank_connected:false,
   payments_enabled:unsafe,quote_preview:true};
  else if(pathname==='/lab/v4/session')result={token:'X'.repeat(64),actor,role:'customer',
   expires_at:1800000000,simulation:true,real_money:false};
  else if(pathname==='/lab/v4/me')result={simulation:true,actor:{actor_id:actor,role:'customer'},
   label:'Sample Customer'};
  else if(pathname==='/lab/v4/quotes' && request.method==='POST'){
   if(failPost)throw new Error('dropped network');
   result=quote;
  }else if(pathname==='/lab/v4/quotes'&&request.method==='GET'){
   result={items:[quote],simulation:true};
  }else if(pathname==='/lab/v4/requests')result={items:[],simulation:true};
  else if(pathname==='/lab/v4/agents')result={items:[],has_more:false,total_matching:0,
   simulation:true,real_location_verified:false};
  else if(pathname==='/lab/v4/notifications')result={items:[],simulation:true};
  else if(pathname==='/lab/v4/logout')result={logged_out:true,simulation:true};
  else result={error:'NOT_FOUND',simulation:true};
  return {status:result.error?404:200,body:JSON.stringify(result),
   url,contentType:'application/json',redirected:false};
 }}};
}
function build(harness){
 return createLabRuntime({baseURL:base,adapter:harness.adapter,
  nowMs:()=>1799999900000,clock:{nowSeconds:()=>1799999900,trustedClock:true}});
}
test('local canned customer session and quote APIs preserve server authority',async()=>{
 const h=createCannedAdapter(),runtime=build(h);
 assert.equal((await runtime.client.health()).acceptsMoney,false);
 assert.equal((await runtime.client.capabilities()).canPostMoney,false);
 const view=await runtime.client.startSession({actor_id:actor,device_id:device,demo_pin:'demo-pin-for-test'});
 assert.equal(view.actor,actor);
 assert.equal(view.balanceAuthority,false);
 const me=await runtime.client.profile();
 assert.equal(me.simulation,true);
 const saved=await runtime.client.newQuote({operation:'transfer',counterpart_id:'sim_customer_beta',
  principal_poisha:poisha(10000),source_ref:'quote_test0001',lifetime_seconds:180});
 assert.equal(saved.owner,actor);
 assert.equal(saved.total,10000);
 assert.equal(checkFinancialSafety('quote',saved).passed,true);
 const list=await runtime.client.quotes();
 assert.equal(list.length,1);
 assert.equal(runtime.client.mayExecutePayment(),false);
 assert.throws(()=>runtime.client.executePayment());
 const logged=h.history.filter(x=>x.path.startsWith('/lab/v4/quotes'));
 assert.equal(logged.length,2);
 assert.equal(logged[0].headers['X-Sim-Device'],device);
 assert.equal(logged[0].headers['Content-Type'],'application/json');
 await runtime.client.endSession();
 assert.equal(runtime.session.status(),'revoked');
 assert.equal(runtime.cache.size(),0);
 runtime.dispose();
});
test('untrusted server identity is never displayed as caller-owned',async()=>{
 const h=createCannedAdapter({wrongOwner:true}),runtime=build(h);
 await runtime.client.startSession({actor_id:actor,device_id:device,demo_pin:'demo-pin-for-test'});
 await assert.rejects(()=>runtime.client.quotes(),e=>e instanceof LabClientError&&e.code==='ROLE_FORBIDDEN');
 runtime.dispose();
});
test('capability escalation fails before client enrollment',async()=>{
 const h=createCannedAdapter({unsafe:true}),runtime=build(h);
 await assert.rejects(()=>runtime.client.capabilities(),e=>e.code==='UNSAFE_CAPABILITY');
 runtime.dispose();
});
test('uncertain quote POST is not automatically repeated',async()=>{
 const h=createCannedAdapter({failPost:true}),runtime=build(h);
 await runtime.client.startSession({actor_id:actor,device_id:device,demo_pin:'demo-pin-for-test'});
 await assert.rejects(()=>runtime.client.newQuote({operation:'transfer',counterpart_id:'sim_customer_beta',
  principal_poisha:poisha(10000),source_ref:'quote_test0002',lifetime_seconds:180}));
 assert.equal(h.history.filter(x=>x.path==='/lab/v4/quotes'&&x.method==='POST').length,1);
 runtime.dispose();
});
test('startLocalDemo verifies capability, creates ephemeral auth, then cleans up',async()=>{
 const h=createCannedAdapter();
 const result=await startLocalDemo({baseURL:base,adapter:h.adapter,
  demoActor:actor,demoDevice:device,demoPin:'demo-pin-for-test',optInToFictionalData:true});
 assert.equal(result.actualFinancialServicesEnabled,false);
 assert.equal(result.runtime.session.status(),'active');
 await stopLocalDemo(result);
 assert.equal(result.runtime.session.debug().hasBearer,false);
});
test('operator credentials are never accepted as an SDK configuration',()=>{
 const h=createCannedAdapter();
 assert.throws(()=>createLabRuntime({baseURL:'https://api.bank.example',adapter:h.adapter}));
});
