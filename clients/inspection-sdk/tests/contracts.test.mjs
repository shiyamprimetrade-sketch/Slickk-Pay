import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseBdt, formatBdt, cashoutPilotQuote, merchantPilotQuote,
  parseHealth, parseAccount, parseChainProof, parseReconciliation,
  ReadOnlySandboxClient, SandboxApiError, message} from '../dist/index.js';

test('exact BDT literal arithmetic', () => {
  assert.equal(parseBdt('10.99'),1099n);
  assert.equal(formatBdt(1099n),'10.99');
  assert.equal(formatBdt(-1099n),'-10.99');
  for(const value of ['NaN','1e4','1.000','-1','1,000','Infinity',' 1.00']) {
    assert.throws(()=>parseBdt(value));
  }
});

test('pilot fees are exact and educational only', () => {
  const quote=cashoutPilotQuote(100000n);
  assert.equal(quote.fee,1099n);
  assert.equal(quote.commission,550n);
  assert.equal(quote.total,101099n);
  assert.equal(merchantPilotQuote(100000n).merchantFee,450n);
});

test('health never accepts live-money claims',()=>{
  assert.equal(parseHealth({simulation:true,ledger_backend:'sqlite',checkouts_enabled:false,
    connected_to_external_banks:false,interface:'READ_ONLY'}).simulation,true);
  assert.throws(()=>parseHealth({simulation:false,ledger_backend:'sqlite',checkouts_enabled:false,
    connected_to_external_banks:false,interface:'READ_ONLY'}));
});

test('ledger proof rejects contradiction',()=>{
  const digest='0'.repeat(64);
  assert.equal(parseChainProof({simulation:true,count:0,valid:true,latest_hash:digest,
    total_debits:0,total_credits:0,mismatches:[]}).valid,true);
  assert.throws(()=>parseChainProof({simulation:true,count:1,valid:true,latest_hash:digest,
    total_debits:100,total_credits:0,mismatches:[]}));
});

test('account parser verifies synthetic identity and safe amount',()=>{
  const raw={account_id:'sim_account_0001',owner_id:'sim_owner_0001',kind:'customer',
    poisha:150,version:1,frozen:false,simulation:true};
  assert.equal(parseAccount(raw).poisha,150);
  assert.throws(()=>parseAccount({...raw,poisha:1.25}));
  assert.throws(()=>parseAccount({...raw,account_id:'bank_account_01'}));
});

test('reconciliation report checks arithmetic',()=>{
  const base={simulation:true,reference:'sim_recon_12345',account_id:'sim_account_0001',
    date:'2026-11-03',opening_poisha:100,debit_poisha:25,credit_poisha:5,
    expected_poisha:80,observed_poisha:80,matched:true,evidence_digest:'a'.repeat(64)};
  assert.equal(parseReconciliation(base).matched,true);
  assert.throws(()=>parseReconciliation({...base,expected_poisha:81}));
});

test('read-only client never requests an unsafe origin',()=>{
  const config={operatorKey:()=> 'K'.repeat(64)};
  assert.throws(()=>new ReadOnlySandboxClient({...config,baseUrl:'http://untrusted.example'}));
  assert.throws(()=>new ReadOnlySandboxClient({...config,baseUrl:'https://name:password@example.com'}));
});

test('network reads require explicit simulation flags',async()=>{
  const seen=[];
  const fakeFetch=async(url,options)=>{
    seen.push({url,method:options.method,cache:options.cache,credentials:options.credentials});
    return new Response(JSON.stringify({simulation:true,ledger_backend:'sqlite',
      checkouts_enabled:false,connected_to_external_banks:false,interface:'READ_ONLY'}),
      {status:200,headers:{'content-type':'application/json'}});
  };
  const client=new ReadOnlySandboxClient({baseUrl:'http://localhost:5000',
    operatorKey:()=> 'K'.repeat(64),fetcher:fakeFetch});
  assert.equal((await client.health()).interface,'READ_ONLY');
  assert.equal(seen[0].method,'GET');
  assert.equal(seen[0].cache,'no-store');
  assert.equal(seen[0].credentials,'omit');
});

test('Bangla and English labels preserve simulation warning',()=>{
  assert.match(message('en','fictional'),/Fictional/);
  assert.match(message('bn','fictional'),/কাল্পনিক/);
});
