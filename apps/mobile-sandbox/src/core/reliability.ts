/** Failure injection and read-only recovery, without retrying financial mutations. */
import type {AppSnapshot,UiNetwork} from "./types.js";
import {assertFixtureOnly,backoffSchedule} from "./offline.js";
export type SimulatedFailure="dns"|"timeout"|"bad_json"|"stale_snapshot"|"clock_rollback"|"network_partition";
export interface RecoveryLog {readonly at:string;readonly failure:SimulatedFailure;readonly action:string;readonly persistedFinancialCommand:false;readonly attemptedFinancialPosting:false;}
export interface RecoveryState {readonly network:UiNetwork;readonly failCount:number;readonly nextReadAllowedAt:number;readonly lastGoodFixture:AppSnapshot|null;readonly logs:readonly RecoveryLog[];readonly canReplayPayments:false;}
export class RecoveryError extends Error{constructor(readonly code:string){super(code);this.name="RecoveryError";}}
export class ReadOnlyRecovery{
 private network:UiNetwork="offline";
 private failures=0;
 private retryAt=0;
 private fixture:AppSnapshot|null=null;
 private logs:RecoveryLog[]=[];
 setNetwork(value:UiNetwork):void{if(!["online","offline","limited"].includes(value))throw new RecoveryError("INVALID_NETWORK");this.network=value;}
 acceptFixture(snapshot:AppSnapshot,now:number):void{
  if(!Number.isSafeInteger(now)||now<0)throw new RecoveryError("BAD_CLOCK");
  assertFixtureOnly(snapshot);
  this.fixture=snapshot;this.failures=0;this.retryAt=0;
 }
 inject(failure:SimulatedFailure,now:number):RecoveryState{
  if(!Number.isSafeInteger(now)||now<0)throw new RecoveryError("BAD_CLOCK");
  if(!["dns","timeout","bad_json","stale_snapshot","clock_rollback","network_partition"].includes(failure))throw new RecoveryError("INVALID_FAILURE");
  this.failures=Math.min(this.failures+1,12);
  this.retryAt=now+backoffSchedule(this.failures-1);
  this.logs.push(Object.freeze({at:new Date(now).toISOString(),failure,
   action:failure==="network_partition"?"SHOW_STALE_FIXTURE":"DEFER_READ_ONLY_RETRY",
   persistedFinancialCommand:false,attemptedFinancialPosting:false}));
  if(this.logs.length>100)this.logs.shift();
  return this.snapshot();
 }
 canRead(now:number):boolean{return this.network==="online"&&now>=this.retryAt;}
 snapshot():RecoveryState{
  return Object.freeze({network:this.network,failCount:this.failures,nextReadAllowedAt:this.retryAt,
   lastGoodFixture:this.fixture,logs:Object.freeze([...this.logs]),canReplayPayments:false});
 }
 attemptWrite():never{throw new RecoveryError("NO_FINANCIAL_REPLAY_QUEUE");}
 clearOnPersonaSwitch():void{this.fixture=null;this.logs=[];this.failures=0;this.retryAt=0;}
}
export function recoveryPlan(state:RecoveryState,now:number):{retryRead:boolean;showFixture:boolean;postingEnabled:false;reason:string}{
 if(!Number.isFinite(now)||now<0)throw new RecoveryError("INVALID_TIME");
 if(state.network!=="online")return {retryRead:false,showFixture:state.lastGoodFixture!==null,postingEnabled:false,reason:"NETWORK_UNAVAILABLE"};
 if(now<state.nextReadAllowedAt)return {retryRead:false,showFixture:state.lastGoodFixture!==null,postingEnabled:false,reason:"BACKOFF_ACTIVE"};
 return {retryRead:true,showFixture:state.lastGoodFixture!==null,postingEnabled:false,reason:"READ_ONLY_RETRY"};
}
export function recoveryAudit(logs:readonly RecoveryLog[]):{count:number;anyPosted:boolean;failureKinds:readonly SimulatedFailure[]}{
 return {count:logs.length,anyPosted:logs.some(x=>x.attemptedFinancialPosting||x.persistedFinancialCommand),
  failureKinds:Object.freeze([...new Set(logs.map(x=>x.failure))])};
}
export function preserveDraftAfterCrash(_raw:unknown):null{
 // Never restore untrusted financial intents from shared device storage after a crash.
 return null;
}
export function permittedRetries():readonly {action:string;allowed:boolean}[]{
 return Object.freeze([
  {action:"fetch_fixtures",allowed:true},{action:"recheck_readonly_health",allowed:true},
  {action:"retry_local_translations",allowed:true},{action:"retry_transfer_post",allowed:false},
  {action:"retry_agent_cash_out",allowed:false},{action:"retry_payment_capture",allowed:false},
  {action:"retry_loan_disbursement",allowed:false},{action:"retry_provider_webhook",allowed:false},
 ]);
}
export function networkPartitionDisclosure():string{return "A network partition may leave server state unknown; never repeat a payment based on a client timeout.";}
export function failureInjectionMatrix():readonly {name:SimulatedFailure;expected:string}[]{
 return Object.freeze([
  {name:"dns",expected:"Read-only refresh pauses"},
  {name:"timeout",expected:"Read-only refresh uses bounded backoff"},
  {name:"bad_json",expected:"Unverified response is rejected"},
  {name:"stale_snapshot",expected:"Old data remains explicitly marked stale"},
  {name:"clock_rollback",expected:"Session and quote cannot be trusted"},
  {name:"network_partition",expected:"No financial intent is replayed"},
 ]);
}
