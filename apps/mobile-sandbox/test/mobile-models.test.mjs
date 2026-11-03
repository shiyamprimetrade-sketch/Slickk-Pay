import test from 'node:test';import assert from 'node:assert/strict';
import {sampleSnapshot,allSampleAgents} from '../dist/core/fixtures.js';
import {dashboardForSnapshot,dashboardLabels,activitySuccessRate,noRealDataMetric} from '../dist/core/analytics.js';
import {agentCommissionEstimate,agentDailyOperations,directoryAgents,checkAgentAvailability,liquidityWarnings} from '../dist/core/agents.js';
import {merchantInvoice,estimateMerchantStatement,refundPreview,merchantCapabilities} from '../dist/core/merchants.js';
import {receiptFromTransaction,receiptProofWarning,serializeReceiptAsText} from '../dist/core/receipts.js';
import {prepareSupportDraft,submitSupportTicket,suggestSupportCategory,supportSafetyWarnings} from '../dist/core/support.js';
import {auditMobileSnapshot,releaseGates} from '../dist/core/audit.js';
import {localHealthReport,mobileCapabilityAudit} from '../dist/core/health.js';
import {chooseResourceBudget,windowRows,respectResponseBudget} from '../dist/core/performance.js';
import {readableContrastRatio,meetsReadableContrast,layoutForWidth,quoteAccessibility} from '../dist/core/accessibility.js';
import {LocalPreferenceStore,DEFAULT_PREFERENCES,privacyAuditPreferences} from '../dist/core/preferences.js';
import {initialOnboarding,onboardingNext,onboardingPersona,onboardingPrivacy,onboardingConsent,onboardingCompleted} from '../dist/core/onboarding.js';
import {calculatePilotQuote} from '../dist/core/money.js';
const at='2026-11-03T12:00:00Z';
test('customer and agent analytics never imply a live bank',()=>{
 const c=dashboardForSnapshot(sampleSnapshot('customer','en'));
 const a=dashboardForSnapshot(sampleSnapshot('agent','en'));
 assert.equal(c.externalSettlementVerified,false);
 assert.equal(a.externalSettlementVerified,false);
 assert.ok(dashboardLabels(c,'bn').every(x=>x.caveat.length>0));
 assert.equal(noRealDataMetric().real_revenue_poisha,0);
});
test('agent directory and commission models use fictional inventories',()=>{
 const agents=allSampleAgents();
 assert.equal(directoryAgents(agents,{acceptingOnly:true}).length,2);
 assert.equal(checkAgentAvailability(agents[0],'cash_out',800000,1000000),'sample_low_cash');
 assert.equal(agentCommissionEstimate(100000,100000),700);
 assert.ok(liquidityWarnings(100,100,10000).length>=2);
});
test('merchant estimates disclose absence of settlement',()=>{
 const snap=sampleSnapshot('merchant','en');
 const statement=estimateMerchantStatement(snap.transactions,snap.actor.id);
 assert.equal(statement.actualBankSettlementVerified,false);
 assert.equal(merchantCapabilities().settleToBank,false);
 assert.equal(refundPreview(10000,2000,1000).permittedLocally,false);
});
test('sample merchant invoices are never paid or sent',()=>{
 const invoice=merchantInvoice('sim_merchant_0001','Sample books',2,1999,at);
 assert.equal(invoice.totalPoisha,3998);
 assert.equal(invoice.serverSubmitted,false);
 assert.equal(invoice.state,'draft');
 assert.throws(()=>merchantInvoice('sim_merchant_0001','Bad quantity',0,100,at));
});
test('sample receipts contain warnings and are not signatures',()=>{
 const tx=sampleSnapshot().transactions[0];
 const receipt=receiptFromTransaction(tx,{locale:'en'});
 assert.equal(receipt.simulation,true);
 assert.equal(receiptProofWarning(receipt).includes('NOT_PROOF_OF_PAYMENT'),true);
 assert.match(serializeReceiptAsText(receipt),/SIMULATION ONLY/);
 assert.equal(receipt.digest.length,8);
});
test('support drafts cannot be sent and redact sensitive data',()=>{
 const draft=prepareSupportDraft('sim_cust_0001',{subject:'Sample support case',category:'agent',description:'This is a hypothetical dispute scenario only.'},at);
 assert.equal(draft.ok,true);
 if(draft.ok)assert.throws(()=>submitSupportTicket(draft.value));
 assert.equal(suggestSupportCategory('cash handover'), 'agent');
 assert.equal(supportSafetyWarnings('password=secret').length,1);
});
test('mobile audit exposes unknown release gates',()=>{
 const snap=sampleSnapshot();const report=auditMobileSnapshot(snap);
 assert.equal(report.independentSecurityReview,false);
 assert.equal(report.liveReleaseApproved,false);
 assert.equal(releaseGates().every(x=>x.complete===false),true);
 assert.equal(localHealthReport(snap,at).canPostFunds,false);
 assert.equal(mobileCapabilityAudit().hasNativeAndroidBuildProof,false);
});
test('resource budget avoids authoritative caching on low-memory devices',()=>{
 const budget=chooseResourceBudget({memoryClass:'low',network:'limited',batteryLow:true,reduceMotion:true});
 assert.equal(budget.paymentCaching,false);
 assert.equal(budget.maxRows,12);
 assert.equal(windowRows(Array.from({length:40},(_,i)=>i),0,budget).visible.length,12);
 assert.equal(respectResponseBudget({small:'ok'},budget),true);
});
test('contrast and navigation width checks are deterministic',()=>{
 assert.equal(meetsReadableContrast('#000000','#FFFFFF'),true);
 assert.equal(meetsReadableContrast('#FFFFFF','#FFFFFF'),false);
 assert.equal(layoutForWidth(360),'narrow');
 assert.equal(layoutForWidth(500),'medium');
 assert.equal(layoutForWidth(820),'wide');
 assert.throws(()=>readableContrastRatio('invalid','#FFFFFF'));
});
test('financial quote announcements identify demo status',()=>{
 const quote=calculatePilotQuote('cash_out',100000,'2026-11-03T12:02:00Z');
 const message=quoteAccessibility(quote,'en');
 assert.equal(message.financialAction,false);
 assert.match(message.text,/server/i);
});
test('preferences never persist balances or credentials',()=>{
 const pref=new LocalPreferenceStore(DEFAULT_PREFERENCES);
 pref.update({locale:'en',textScale:1.3},at);
 assert.equal(pref.snapshot().locale,'en');
 assert.ok(pref.audit().length>=1);
 assert.deepEqual(privacyAuditPreferences({locale:'en',token:'topsecret'}),['UNSAFE_STORAGE:token']);
});
test('onboarding cannot skip privacy or demo acknowledgment',()=>{
 let s=initialOnboarding('en');s=onboardingNext(s,at);
 assert.throws(()=>onboardingNext(s,at));
 s=onboardingPersona(s,'customer');s=onboardingNext(s,at);
 assert.throws(()=>onboardingNext(s,at));
 s=onboardingPrivacy(s,true);s=onboardingNext(s,at);
 assert.throws(()=>onboardingNext(s,at));
 s=onboardingConsent(s,true);s=onboardingNext(s,at);
 assert.equal(onboardingCompleted(s).ready,true);
 assert.equal(onboardingCompleted(s).kycVerified,false);
});
