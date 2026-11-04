import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
 health,capabilities,parseDemoProfile,parseSyntheticBalances,
 parseDirectory,parseActivityPage,parseQuote,parseReview,
 parseSupportCase,verifyContract,checkFinancialSafety,
 FinancialSafetyMonitor,poisha
} from '../dist/index.js';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/cycle004-actual-shapes.json',import.meta.url),'utf8'));
const actor='sim_customer_alpha';
test('actual Cycle 004 Python health and capabilities match SDK',()=>{
 assert.equal(health(fixture.health).acceptsMoney,false);
 assert.equal(capabilities(fixture.capabilities).canPostMoney,false);
 assert.equal(fixture.health.posting_enabled,false);
});
test('actual Python persona and synthetic account shape is accepted',()=>{
 const p=parseDemoProfile(fixture.me);
 assert.equal(p.id,actor);
 assert.equal(p.liveKycVerified,false);
 const balances=parseSyntheticBalances(fixture.me,actor);
 assert.equal(balances.length,1);
 assert.equal(balances[0].amount,100000);
 assert.equal(balances[0].authoritative,false);
});
test('actual Python agent directory and empty activity feed',()=>{
 const d=parseDirectory(fixture.agents);
 assert.equal(d.items[0].acceptsRealCash,false);
 const activity=parseActivityPage(fixture.activity,actor);
 assert.deepEqual(activity,[]);
});
test('actual Python quote and review are coherent and non-posting',()=>{
 const q=parseQuote(fixture.quote),r=parseReview(fixture.review);
 assert.equal(q.id,r.quoteId);
 assert.equal(q.owner,r.owner);
 assert.equal(r.financialPosting,false);
 assert.equal(q.principal,poisha(10000));
 assert.equal(verifyContract('quote',fixture.quote).passed,true);
 assert.equal(verifyContract('request',fixture.review).passed,true);
});
test('real support draft omits owner but is bound to authenticated caller',()=>{
 const support=parseSupportCase(fixture.support,actor);
 assert.equal(support.category,'privacy');
 assert.equal(support.owner,actor);
 assert.equal(support.externallySubmitted,false);
 assert.throws(()=>parseSupportCase(fixture.support));
});
test('financial safety monitor rejects fake settled request',()=>{
 const monitor=new FinancialSafetyMonitor();
 assert.equal(monitor.check('quote',parseQuote(fixture.quote)).passed,true);
 assert.equal(monitor.check('request',parseReview(fixture.review)).passed,true);
 assert.equal(monitor.report().passed,true);
 assert.equal(monitor.report().productionApproved,false);
});
