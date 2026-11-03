/** Offline behavior: show fictional fixtures, but never queue financially authoritative commands. */
import type {FetchStatus,UiNetwork,AppSnapshot,PaymentDraft,ActionAvailability,Locale} from "./types.js";
import {redactLogRecord} from "./privacy.js";
export type QueueItemKind="preference_change"|"screen_view"|"demo_draft";
export interface LocalEvent {readonly id:string;readonly kind:QueueItemKind;readonly at:string;readonly payload:Readonly<Record<string,string>>;readonly syncable:false;}
export interface OfflineSnapshot {readonly status:FetchStatus;readonly events:readonly LocalEvent[];readonly simulation:true;readonly balanceAuthoritative:false;readonly paymentQueueLength:0;}
export class OfflineError extends Error {constructor(readonly code:string){super(code);this.name="OfflineError";}}
export class OfflineWorkspace {
 private network:UiNetwork="offline";
 private lastAttempt:string|null=null;
 private readonly events:LocalEvent[]=[];
 private revision=0;
 constructor(private readonly source:"fixtures"|"sandbox_server"="fixtures"){}
 setNetwork(value:UiNetwork,now:string):void{
  if(!["online","offline","limited"].includes(value))throw new OfflineError("INVALID_NETWORK");
  if(!Number.isFinite(Date.parse(now)))throw new OfflineError("INVALID_TIME");
  this.network=value;this.lastAttempt=now;
 }
 record(kind:QueueItemKind,payload:Readonly<Record<string,string>>,now:string):LocalEvent{
  if(!["preference_change","screen_view","demo_draft"].includes(kind))throw new OfflineError("UNSUPPORTED_EVENT");
  if(Object.keys(payload).length>8)throw new OfflineError("TOO_MANY_FIELDS");
  const safe:Record<string,string>={};
  for(const [key,value] of Object.entries(payload)){
   if(!/^[a-z_]{2,40}$/.test(key)||value.length>100)throw new OfflineError("INVALID_EVENT_DATA");
   if(/(?:token|pin|password|secret|balance|account|key)/i.test(key))throw new OfflineError("SENSITIVE_EVENT_KEY");
   const redacted=redactLogRecord(value);
   if(redacted!==value)throw new OfflineError("SENSITIVE_EVENT_VALUE");
   safe[key]=value;
  }
  const event=Object.freeze({id:`sim_local_${String(++this.revision).padStart(8,"0")}`,kind,
    at:now,payload:Object.freeze(safe),syncable:false as const});
  this.events.push(event);
  if(this.events.length>100)this.events.shift();
  return event;
 }
 attemptFinancialQueue(_draft:PaymentDraft):never{throw new OfflineError("FINANCIAL_OFFLINE_QUEUE_PROHIBITED");}
 getStatus(now:string):FetchStatus{
  const stale=this.source==="fixtures"||this.network!=="online";
  return Object.freeze({lastAttemptAt:this.lastAttempt,lastSuccessAt:null,network:this.network,
    serverVerified:false,stale,source:this.source});
 }
 snapshot(now:string):OfflineSnapshot{
  return Object.freeze({status:this.getStatus(now),events:Object.freeze([...this.events]),
   simulation:true,balanceAuthoritative:false,paymentQueueLength:0});
 }
 clear():void{this.events.length=0;this.revision=0;}
}
export function networkLabel(locale:Locale,network:UiNetwork):string{
 const en:Record<UiNetwork,string>={offline:"Offline preview",limited:"Limited connectivity",online:"Online · not payment-authorized"};
 const bn:Record<UiNetwork,string>={offline:"অফলাইন নমুনা",limited:"সীমিত সংযোগ",online:"অনলাইন · লেনদেন অনুমোদিত নয়"};
 return (locale==="bn"?bn:en)[network];
}
export function availabilityUnderNetwork(network:UiNetwork,action:"view"|"quote"|"confirm"|"withdraw"|"support"):ActionAvailability{
 if(action==="view"||action==="quote")return {enabled:true,needsServer:false,reason:"LOCAL_SAMPLE_ONLY"};
 return {enabled:false,needsServer:true,reason:network==="offline"?"OFFLINE_SERVER_REQUIRED":"NO_LIVE_FINANCIAL_API"};
}
export function assertFixtureOnly(snapshot:AppSnapshot):void{
 if(snapshot.simulation!==true||snapshot.dataProvenance!=="fixture")throw new OfflineError("UNVERIFIED_SNAPSHOT");
 if(snapshot.accounts.some(x=>!x.simulation||x.dataProvenance!=="fixture"))throw new OfflineError("EXTERNAL_ACCOUNT");
 if(snapshot.transactions.some(x=>!x.simulation))throw new OfflineError("UNVERIFIED_HISTORY");
}
export function purgeOnAccountSwitch(_current:AppSnapshot):{clearDrafts:true;clearReceipts:true;clearNotices:true;clearQueries:true}{
 return {clearDrafts:true,clearReceipts:true,clearNotices:true,clearQueries:true};
}
export interface RefreshPlan {readonly attempt:boolean;readonly reason:string;readonly minimumWaitMs:number;readonly mayWritePayments:false;}
export function planRefresh(status:FetchStatus,now:string,foreground:boolean):RefreshPlan{
 const time=Date.parse(now);if(!Number.isFinite(time))throw new OfflineError("INVALID_CLOCK");
 if(!foreground)return {attempt:false,reason:"BACKGROUND",minimumWaitMs:0,mayWritePayments:false};
 if(status.network!=="online")return {attempt:false,reason:"NO_NETWORK",minimumWaitMs:0,mayWritePayments:false};
 if(status.source==="fixtures")return {attempt:false,reason:"LOCAL_FIXTURE_SOURCE",minimumWaitMs:0,mayWritePayments:false};
 if(status.lastAttemptAt){
  const elapsed=time-Date.parse(status.lastAttemptAt);
  if(!Number.isFinite(elapsed)||elapsed<0)return {attempt:false,reason:"UNRELIABLE_CLOCK",minimumWaitMs:0,mayWritePayments:false};
  if(elapsed<10_000)return {attempt:false,reason:"RATE_LIMIT",minimumWaitMs:10_000-elapsed,mayWritePayments:false};
 }
 return {attempt:true,reason:"READ_ONLY_REFRESH",minimumWaitMs:0,mayWritePayments:false};
}
export function backoffSchedule(attempt:number,seed=0):number{
 if(!Number.isSafeInteger(attempt)||attempt<0||attempt>12)throw new OfflineError("INVALID_RETRY");
 if(!Number.isSafeInteger(seed)||seed<0||seed>1000)throw new OfflineError("INVALID_SEED");
 return Math.min(30_000,500*2**attempt)+seed;
}
export function shouldExpireFixture(lastSeen:string,now:string,ttlMinutes=15):boolean{
 if(!Number.isSafeInteger(ttlMinutes)||ttlMinutes<1||ttlMinutes>1440)throw new OfflineError("INVALID_TTL");
 const from=Date.parse(lastSeen),to=Date.parse(now);
 if(!Number.isFinite(from)||!Number.isFinite(to)||to<from)return true;
 return to-from>ttlMinutes*60_000;
}
export function compareSnapshotVersions(old:AppSnapshot,updated:AppSnapshot):{safe:boolean;issues:readonly string[]}{
 const problems:string[]=[];
 if(updated.actor.id!==old.actor.id)problems.push("ACTOR_SWITCH");
 if(updated.dataProvenance!=="fixture"||!updated.simulation)problems.push("PROVENANCE_CHANGE");
 if(updated.accounts.some(x=>!Number.isSafeInteger(x.poisha)))problems.push("INVALID_AMOUNT");
 if(updated.updatedAt<old.updatedAt)problems.push("STALE_CLOCK");
 return {safe:problems.length===0,issues:Object.freeze(problems)};
}
export function noBackgroundValueMovement():Readonly<Record<string,boolean>>{
 return Object.freeze({allowBalanceCache:false,allowOfflineTransfers:false,allowOfflineCashOut:false,
  allowOfflineRefunds:false,allowPendingPaymentReplay:false,allowReadOnlyFixtureDisplay:true});
}
