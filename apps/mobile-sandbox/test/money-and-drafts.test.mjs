import test from 'node:test';
import assert from 'node:assert/strict';
import {assertPoisha,addPoisha,subtractPoisha,multiplyRatio,parseBDT,formatBDT,percentBasisPoints,calculatePilotQuote,verifyQuote,quoteMargin,splitPoisha} from '../dist/core/money.js';
import {createDraft,quoteDraft,reviewDraft,cancelDraft,expireDraft,editDraftAmount,compareDraftRevisions,DraftWorkspace,draftAvailability} from '../dist/core/drafts.js';
const at='2026-11-03T12:00:00Z';
const later='2026-11-03T12:01:00Z';
const far='2026-11-03T12:05:00Z';
const create=()=>createDraft({ownerId:'sim_cust_0001',operation:'transfer',recipientId:'sim_cust_0002',amountText:'1000.00',note:'For sample goods'},at);
test('exact poisha arithmetic and overflow guards',()=>{
 assert.equal(parseBDT('1000.99'),100099);assert.equal(parseBDT('0.01'),1);assert.throws(()=>parseBDT('001.00'));
});
// Amount parser rejects ambiguous leading zeroes and excess fraction precision.
test('parse amount rejects ambiguous numeric forms',()=>{
 for(const amount of ['01.00','1.001','1e2','-1','NaN','Infinity','1,000.00','','.50'])assert.throws(()=>parseBDT(amount));
 assert.equal(parseBDT('100.1'),10010);assert.equal(formatBDT(10010,'en'), '৳100.10');
});
test('minor unit operations never round through floating values',()=>{
 assert.equal(addPoisha(1,2,3),6);assert.equal(subtractPoisha(3,2),1);assert.throws(()=>subtractPoisha(1,2));
 assert.throws(()=>assertPoisha(1.1));assert.throws(()=>assertPoisha(-1));assert.throws(()=>addPoisha(Number.MAX_SAFE_INTEGER));
 assert.equal(multiplyRatio(100,1,3,'half_up'),33);assert.equal(multiplyRatio(100,1,3,'ceil'),34);
 assert.equal(percentBasisPoints(100000,45),450);
});
test('sample pilot fees are exact and disclose the total',()=>{
 const x=calculatePilotQuote('cash_out',100000,far);
 assert.equal(x.customerFeePoisha,1099);assert.equal(x.agentCommissionPoisha,550);
 assert.equal(x.customerDebitPoisha,101099);assert.equal(x.taxPoisha,0);
 assert.equal(calculatePilotQuote('cash_in',100000,far).agentCommissionPoisha,150);
 assert.equal(calculatePilotQuote('merchant_payment',100000,far).merchantFeePoisha,450);
 assert.equal(calculatePilotQuote('transfer',100000,far).customerFeePoisha,0);
 assert.equal(x.basis,'unapproved_pilot_hypothesis');
});
test('merchant fee and commission do not become a bank settlement',()=>{
 const q=calculatePilotQuote('merchant_payment',250000,far);
 assert.equal(q.customerDebitPoisha,250000);assert.equal(q.recipientCreditPoisha+q.merchantFeePoisha,250000);
 assert.equal(quoteMargin(q,100,100,100),q.merchantFeePoisha-300);
});
test('quote is not valid past its expiry',()=>{
 const q=calculatePilotQuote('cash_in',10000,far);
 assert.equal(verifyQuote(q,at),true);assert.equal(verifyQuote(q,'2026-11-03T12:06:00Z'),false);
});
test('split of uneven amounts conserves poisha',()=>{
 assert.deepEqual(splitPoisha(101,3),[34,34,33]);assert.equal(splitPoisha(1,3).reduce((a,b)=>a+b,0),1);
 assert.throws(()=>splitPoisha(1,0));
});
test('draft lifecycle cannot manufacture server approval',()=>{
 const original=create();assert.equal(original.serverState,'not_sent');
 const quoted=quoteDraft(original,at);assert.equal(quoted.state,'quoted');
 const reviewed=reviewDraft(quoted,later,true);
 assert.equal(reviewed.draft.serverState,'not_sent');assert.equal(reviewed.canPost,false);
 assert.equal(reviewed.draft.approval,'requires_server');
 assert.equal(draftAvailability(reviewed.draft,'online').enabled,false);
 assert.throws(()=>quoteDraft(reviewed.draft,far));
});
test('draft cannot be reviewed without explicit simulation acknowledgment',()=>{
 assert.throws(()=>reviewDraft(quoteDraft(create(),at),at,false),/SIMULATION_ACK_REQUIRED/);
});
test('expired drafts never restart financial posting',()=>{
 const draft=quoteDraft(create(),at);
 assert.equal(expireDraft(draft,far).state,'expired');
 assert.throws(()=>quoteDraft(expireDraft(draft,far),far));
 assert.equal(cancelDraft(create(),at).state,'cancelled');
});
test('draft revisions are immutable and monotonic',()=>{
 const original=create(),newer=editDraftAmount(original,'1200.00',later);
 assert.equal(original.principalPoisha,100000);assert.equal(newer.principalPoisha,120000);
 assert.deepEqual(compareDraftRevisions(original,newer),['principal']);
 assert.throws(()=>compareDraftRevisions(newer,original));
});
test('workspace ownership and duplicated review guards',()=>{
 const ws=new DraftWorkspace('sim_cust_0001');
 const d=ws.create({ownerId:'sim_cust_0001',operation:'transfer',recipientId:'sim_cust_0002',amountText:'20.00'},at);
 const q=ws.update(d.id,'quote',at);
 assert.equal(ws.get(d.id).state,'quoted');
 assert.equal(ws.review(d.id,later,true).draft.state,'reviewed');
 assert.throws(()=>ws.discard(d.id));
 assert.equal(ws.eventHistory(d.id).length,3);
 assert.throws(()=>ws.create({ownerId:'sim_other_0001',operation:'transfer',recipientId:'sim_cust_0002',amountText:'20.00'},at));
});
