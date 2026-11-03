import test from 'node:test';import assert from 'node:assert/strict';
import {sampleSnapshot,fixtureActor,fixtureIntegrity,allSampleAgents} from '../dist/core/fixtures.js';
import {validateTranslations,t,operationLabel,statusLabel,localTime} from '../dist/core/locales.js';
import {auditPrivateSnapshot,maskIdentifier,maskEmail,redactLogRecord,piiRiskScore} from '../dist/core/privacy.js';
import {normalizeBdPhone,maskPhone,checkSafeNote,checkSyntheticId,validateDraftTarget,validateSupportForm} from '../dist/core/validation.js';
import {buildDemoQR,parseDemoQR,qrActionAvailability,rejectExternalQrScheme} from '../dist/core/qr.js';
import {createDraft} from '../dist/core/drafts.js';
const snap=sampleSnapshot('customer','bn');
test('fixture inventory is synthetic and internally consistent',()=>{
 assert.deepEqual(fixtureIntegrity(),[]);assert.deepEqual(auditPrivateSnapshot(snap),[]);
 assert.equal(snap.actor.verified,false);assert.equal(snap.dataProvenance,'fixture');
 assert.equal(snap.accounts.every(x=>x.ownerId===snap.actor.id),true);
});
test('persona fixtures remain isolated',()=>{
 const a=sampleSnapshot('agent','en'),m=sampleSnapshot('merchant','en');
 assert.equal(a.actor.role,'agent');assert.equal(m.actor.role,'merchant');
 assert.equal(a.accounts.every(x=>x.ownerId===a.actor.id),true);
 assert.equal(m.transactions.every(x=>x.ownerId===m.actor.id),true);
});
test('language tables fully cover all public keys',()=>{
 assert.deepEqual(validateTranslations(),[]);
 assert.equal(t('en','simulationBanner').includes('FICTITIOUS'),true);
 assert.equal(t('bn','simulationBanner').includes('কাল্পনিক'),true);
 assert.notEqual(operationLabel('bn','transfer'),operationLabel('en','transfer'));
 assert.ok(localTime('en','2026-11-03T12:00:00Z').length>0);
});
test('sensitive customer identifiers are masked',()=>{
 assert.equal(normalizeBdPhone('01700000000').ok,true);
 assert.equal(normalizeBdPhone('12345').ok,false);
 assert.equal(maskPhone('01700000000').includes('•••••'),true);
 assert.equal(maskEmail('rahim@example.test'), 'r•••@example.test');
 assert.equal(maskIdentifier('sim_account_0001').includes('••••'),true);
});
test('PII does not enter diagnostic logs',()=>{
 assert.deepEqual(redactLogRecord({token:'abc',nested:{phone:'+8801700000000'}}),{token:'[REDACTED]',nested:{phone:'[REDACTED]'}});
 assert.equal(piiRiskScore({password:'abc',email:'x@example.test'}).score>=2,true);
 assert.equal(checkSafeNote('otp=123456').ok,false);
});
test('strict synthetic target and note validation',()=>{
 assert.equal(checkSyntheticId('real_customer_1').ok,false);
 assert.equal(validateDraftTarget('transfer',null,null,null).ok,false);
 assert.equal(validateDraftTarget('transfer','sim_cust_0002',null,null).ok,true);
 assert.equal(checkSafeNote('Normal groceries').ok,true);
});
test('support form never accepts a credential-like payload',()=>{
 assert.equal(validateSupportForm({subject:'Sample case',category:'technical',description:'This is a harmless fictional support case.'}).ok,true);
 assert.equal(validateSupportForm({subject:'Sample',category:'technical',description:'api_key=live_private_token'}).ok,false);
});
test('QR payload is strictly sandbox-only',()=>{
 const qr=buildDemoQR({kind:'agent',id:'sim_agent_0001',label:'Demo agent',amountPoisha:10000,reference:null});
 const parsed=parseDemoQR(qr);assert.equal(parsed.ok,true);
 if(parsed.ok)assert.equal(qrActionAvailability(parsed.value,'cash_out').canPay,false);
 assert.equal(rejectExternalQrScheme('https://bank.example/pay'),true);
});
test('QR parameter pollution is rejected',()=>{
 const qr=buildDemoQR({kind:'merchant',id:'sim_merchant_0001',label:'Demo store',amountPoisha:null,reference:null});
 assert.equal(parseDemoQR(qr+'&id=sim_other_0001').ok,false);
 assert.equal(parseDemoQR(qr.replace('slickkpaylab:', 'https:')).ok,false);
 assert.equal(parseDemoQR('javascript:alert(1)').ok,false);
});
