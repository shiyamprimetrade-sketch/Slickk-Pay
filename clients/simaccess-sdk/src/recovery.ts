/** Reconnection decision engine: reads may retry, mutations require server lookup. */
import {failure,invariant} from "./errors.js";
export type OperationKind="read"|"preview_mutation"|"money_mutation";
export type AttemptOutcome="completed"|"timeout"|"connection_lost"|"server_rejected"|"unknown";
export type RecoveryDecision="accept"|"retry_read"|"inspect_server"|"stop";
export interface AttemptEvidence {
 readonly route:string;readonly kind:OperationKind;
 readonly attemptId:string;readonly outcome:AttemptOutcome;
 readonly timestamp:number;readonly simulation:true;
}
export interface RecoveryFinding {
 readonly decision:RecoveryDecision;
 readonly mayRetryWithoutLookup:boolean;
 readonly paymentWasAuthorized:false;
 readonly needsServerVerification:boolean;
 readonly explanation:string;
}
export function decideRecovery(evidence:AttemptEvidence):RecoveryFinding {
 const {kind,outcome}=evidence;
 if(kind==="money_mutation")return Object.freeze({
  decision:"stop",mayRetryWithoutLookup:false,paymentWasAuthorized:false,
  needsServerVerification:false,explanation:"Financial mutation is not implemented in the lab"});
 if(outcome==="completed")return Object.freeze({
  decision:"accept",mayRetryWithoutLookup:false,paymentWasAuthorized:false,
  needsServerVerification:false,explanation:"Read or preview response completed"});
 if(outcome==="server_rejected")return Object.freeze({
  decision:"stop",mayRetryWithoutLookup:false,paymentWasAuthorized:false,
  needsServerVerification:false,explanation:"Server explicitly rejected the request"});
 if(kind==="read")return Object.freeze({
  decision:"retry_read",mayRetryWithoutLookup:true,paymentWasAuthorized:false,
  needsServerVerification:false,explanation:"Idempotent read may be repeated"});
 return Object.freeze({decision:"inspect_server",mayRetryWithoutLookup:false,
  paymentWasAuthorized:false,needsServerVerification:true,
  explanation:"Preview mutation outcome is unknown; inspect by reference before another write"});
}
export interface RecoveryRecord {
 readonly event:AttemptEvidence;readonly finding:RecoveryFinding;
 readonly inspectedAt:number|null;readonly finalStatus:string|null;
}
export class RecoveryDesk {
 private readonly entries=new Map<string,RecoveryRecord>();
 constructor(private readonly now:()=>number=()=>Date.now()){}
 observe(evidence:AttemptEvidence):RecoveryRecord{
  if(!/^\/lab\/v4\/[a-z0-9_/-]+$/.test(evidence.route))throw failure("INVALID_INPUT");
  if(!/^[a-z][A-Za-z0-9_:.\-]{7,96}$/.test(evidence.attemptId))throw failure("INVALID_INPUT");
  invariant(Number.isSafeInteger(evidence.timestamp)&&evidence.timestamp>=0);
  const existing=this.entries.get(evidence.attemptId);
  if(existing){
   if(existing.event.kind!==evidence.kind||existing.event.route!==evidence.route)
    throw failure("CONFLICT");
   return existing;
  }
  const finding=decideRecovery(evidence);
  const record=Object.freeze({event:evidence,finding,inspectedAt:null,finalStatus:null});
  this.entries.set(evidence.attemptId,record);
  return record;
 }
 resolve(attemptId:string,serverState:string):RecoveryRecord{
  const existing=this.entries.get(attemptId);
  if(!existing)throw failure("NOT_FOUND");
  if(existing.finding.decision!=="inspect_server")throw failure("REQUEST_FINAL");
  if(!["quoted","reviewed","cancelled","expired","not_found"].includes(serverState))
   throw failure("UNTRUSTED_RESPONSE");
  const replacement:RecoveryRecord=Object.freeze({...existing,inspectedAt:this.now(),finalStatus:serverState});
  this.entries.set(attemptId,replacement);
  return replacement;
 }
 unresolved():readonly RecoveryRecord[]{
  return Object.freeze([...this.entries.values()].filter(x=>x.finding.needsServerVerification&&x.inspectedAt===null));
 }
 wipe():void{this.entries.clear();}
 count():number{return this.entries.size;}
 canRetryMoney():false{return false;}
}
