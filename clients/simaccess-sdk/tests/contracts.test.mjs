import test from 'node:test';
import assert from 'node:assert/strict';
import {
  poisha,fromBdtText,toBdtText,safeAdd,safeSubtract,merchantIllustrativeFee,
  parseQuote,quoteCanBeReviewed,quoteDisclosure,parseReview,neverResumeCancelled,
  parseDialogue,parseChecklist,parseReceipt,parseDirectory,parseAgent,
  parseQrIssue,parseQrInspection,validateSampleQrUri,parseNotice,parseSupportCase,
  readBreakdown,assertNoLiveCapabilities,capabilities,
  verifyContract,ContractSuite,checkFinancialSafety,quoteCard,receiptCard,
  quoteEligibility,parseDemoProfile,releaseView,outstandingEvidence
} from '../dist/index.js';
const actor='sim_customer_alpha',agent='sim_agent_alpha',qid='sim_quote_0001',rid='sim_request_0001';
const quote={quote_id:qid,owner_id:actor,operation:'cash_out',counterpart_id:agent,
 principal_poisha:100000,fee_poisha:1099,total_poisha:101099,version:'pilot-v1',
 status:'quoted',expires_at:1800000000,simulation:true,can_execute:false,real_money:false,tax_unverified:true};
const review={request_id:rid,owner_id:actor,quote_id:qid,operation:'cash_out',status:'reviewed',
 accepted_at:1799999800,updated_at:1799999800,revision:1,simulation:true,
 financial_posting:false,handover_authorized:false};
const dialogue={request_id:rid,customer_id:actor,agent_id:agent,customer_reviewed:true,
 agent_reviewed:true,state:'both_reviewed',created_at:1799999800,updated_at:1799999810,
 simulation:true,both_reviews_not_payment:true,cash_handover_authorized:false,ledger_posting:false};
const checklist={request_id:rid,agent_id:agent,cash_available:true,customer_present:true,
 warnings_acknowledged:true,updated_at:1799999800,simulation:true,handover_authorized:false,ledger_posted:false};
const receipt={request_id:rid,locale:'en',watermark:'SAMPLE ONLY — NOT PROOF OF PAYMENT',
 lines:[{label:'Preview fee',value:'৳10.99'}],payment_proof:false,bank_settlement_proof:false,simulation:true};
const agentRow={actor_id:agent,label:'Sample Agent Alpha',region:'dhaka_demo',
 sample_cash_poisha:200000,sample_float_poisha:500000,accepts_real_cash:false,
 verified_business_location:false,registered_financial_agent:false,simulation:true};
const qr={issuer:actor,recipient:agent,operation:'transfer',amount_poisha:10000,
 expires_at:1800000000,simulation:true,payment_authorized:false};
test('exact BDT money and no negative balances',()=>{
 assert.equal(fromBdtText('10.99'),1099);
 assert.equal(toBdtText(poisha(1099)), '10.99');
 assert.equal(safeAdd(poisha(200),poisha(100)),300);
 assert.equal(safeSubtract(poisha(200),poisha(100)),100);
 assert.throws(()=>safeSubtract(poisha(1),poisha(2)));
 assert.throws(()=>fromBdtText('10.999'));
 assert.throws(()=>poisha(1.5));
 assert.throws(()=>poisha(Number.MAX_SAFE_INTEGER));
});
test('pilot merchant processing fee is not bank settlement',()=>{
 const m=merchantIllustrativeFee(poisha(100000));
 assert.equal(m.merchantFee,450);
 assert.equal(m.sampleNet,99550);
 assert.equal(m.realBankSettlement,null);
 assert.equal(m.rateApproved,false);
});
test('strict quote identity, conservation and expiry',()=>{
 const q=parseQuote(quote);
 assert.equal(q.total,101099);
 assert.equal(quoteCanBeReviewed(q,actor,1799999900),true);
 assert.equal(quoteCanBeReviewed(q,agent,1799999900),false);
 assert.equal(quoteCanBeReviewed(q,actor,1800000000),false);
 assert.throws(()=>parseQuote({...quote,total_poisha:101100}));
 assert.throws(()=>parseQuote({...quote,can_execute:true}));
 assert.throws(()=>parseQuote({...quote,tax_unverified:false}));
 assert.equal(quoteDisclosure(q,'bn').length,4);
});
test('review states and unauthorized reactivation',()=>{
 const r=parseReview(review);
 assert.equal(r.financialPosting,false);
 assert.equal(r.handoverAuthorized,false);
 const cancelled=parseReview({...review,status:'cancelled',revision:2});
 assert.throws(()=>neverResumeCancelled(cancelled,r));
 assert.throws(()=>parseReview({...review,financial_posting:true}));
 assert.equal(checkFinancialSafety('request',r).passed,true);
});
test('two-party review is not a financial authorization',()=>{
 const d=parseDialogue(dialogue);
 assert.equal(d.ledgerPosting,false);
 assert.equal(d.handoverAuthorized,false);
 assert.throws(()=>parseDialogue({...dialogue,ledger_posting:true}));
 assert.throws(()=>parseDialogue({...dialogue,agent_reviewed:false}));
 assert.equal(checkFinancialSafety('cash',d).passed,true);
 const c=parseChecklist(checklist);
 assert.equal(c.handoverAuthorized,false);
 assert.throws(()=>parseChecklist({...checklist,handover_authorized:true}));
});
test('receipt is watermarked and cannot prove settlement',()=>{
 const r=parseReceipt(receipt);
 assert.equal(r.bankSettlementProof,false);
 assert.equal(checkFinancialSafety('receipt',r).passed,true);
 assert.throws(()=>parseReceipt({...receipt,payment_proof:true}));
 assert.throws(()=>parseReceipt({...receipt,watermark:'Paid in full'}));
 assert.equal(receiptCard(r,'en').canSubmitMoney,false);
});
test('agent listings are fictional, never real-time cash availability',()=>{
 const dir=parseDirectory({items:[agentRow],has_more:false,total_matching:1,simulation:true,real_location_verified:false});
 assert.equal(dir.items[0].acceptsRealCash,false);
 assert.throws(()=>parseAgent({...agentRow,accepts_real_cash:true}));
 assert.throws(()=>parseDirectory({items:[agentRow],has_more:false,total_matching:0,simulation:true,real_location_verified:false}));
});
test('QR preview cannot become a payment intent',()=>{
 const preview=parseQrInspection(qr);
 assert.equal(preview.paymentAuthorized,false);
 assert.throws(()=>parseQrInspection({...qr,payment_authorized:true}));
 assert.throws(()=>validateSampleQrUri('https://bkash.com/pay'));
 assert.throws(()=>parseQrIssue({uri:'https://example.com',simulation:true,can_pay:false}));
});
test('notification and support retain demo safety labels',()=>{
 const notice=parseNotice({id:'sim_notice_0001',kind:'security_notice',content:'Local demo login',
 created_at:1799999999,status:'pending',attempts:0,simulation:true,delivery_enabled:false});
 assert.equal(notice.deliveryEnabled,false);
 assert.throws(()=>parseNotice({id:'sim_notice_0001',kind:'security_notice',content:'Bank settled',
 created_at:1799999999,status:'pending',attempts:0,simulation:true,delivery_enabled:false}));
 const support=parseSupportCase({case_id:'sim_support_0001',owner_id:actor,category:'question',
 description:'Sample issue',created_at:1799999999,status:'draft',simulation:true});
 assert.equal(support.externallySubmitted,false);
});
test('no live capability claims accepted',()=>{
 assert.throws(()=>assertNoLiveCapabilities({simulation:true,bank_connected:true}));
 assert.throws(()=>assertNoLiveCapabilities({simulation:false}));
 const c=capabilities({simulation:true,bank_connected:false,quote_preview:true});
 assert.equal(c.canPostMoney,false);
 assert.equal(checkFinancialSafety('capability',c).passed,true);
});
test('conformance suite reports unsafe data',()=>{
 const suite=new ContractSuite();
 assert.equal(suite.add('quote',quote).passed,true);
 assert.equal(suite.add('request',review).passed,true);
 assert.equal(suite.add('cash_dialogue',dialogue).passed,true);
 assert.equal(suite.add('receipt',receipt).passed,true);
 assert.equal(suite.add('quote',{...quote,fee_poisha:10}).passed,false);
 assert.equal(suite.summary().failed,1);
 assert.throws(()=>suite.assertPassed());
});
test('presenters and eligibility cannot act as a bank',()=>{
 const q=parseQuote(quote);
 assert.equal(quoteCard(q,'en').canSubmitMoney,false);
 assert.equal(quoteEligibility('customer',q).financialActivationApproved,false);
 assert.equal(quoteEligibility('agent',q).availableForPreview,false);
});
test('release proof cannot assert banking authorization',()=>{
 const status=releaseView('review_draft',[
  {category:'source_test',verified:true,reference:null,simulation:true}]);
 assert.equal(status.financeProductionAuthorized,false);
 assert.ok(outstandingEvidence(status).includes('regulatory_review'));
});
