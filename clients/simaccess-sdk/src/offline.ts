/** Offline means read-only stale snapshots, never queued transfers or approvals. */
import {failure,invariant} from "./errors.js";
export type NetworkState="offline"|"connecting"|"online"|"degraded";
export interface NetworkSnapshot {
 readonly state:NetworkState;
 readonly lastVerifiedAt:number|null;
 readonly lastFailureAt:number|null;
 readonly pendingFinancialOperations:0;
 readonly simulation:true;
}
export interface NetworkEvent {readonly type:"connected"|"disconnected"|"timeout"|"reset";readonly at:number;}
export class OfflinePolicy {
 private current:NetworkState="offline";
 private lastVerified:number|null=null;
 private lastFailure:number|null=null;
 private readonly history:NetworkEvent[]=[];
 constructor(private readonly now:()=>number=()=>Date.now()){}
 transition(event:NetworkEvent):NetworkSnapshot{
  invariant(Number.isSafeInteger(event.at)&&event.at>=0);
  if(event.type==="connected"){
   this.current="online";
   this.lastVerified=event.at;
  }else if(event.type==="disconnected"){
   this.current="offline";
   this.lastFailure=event.at;
  }else if(event.type==="timeout"){
   this.current="degraded";
   this.lastFailure=event.at;
  }else{
   this.current="offline";
   this.lastVerified=null;
   this.lastFailure=null;
  }
  this.history.push(event);
  if(this.history.length>100)this.history.shift();
  return this.snapshot();
 }
 snapshot():NetworkSnapshot{
  return Object.freeze({state:this.current,lastVerifiedAt:this.lastVerified,
   lastFailureAt:this.lastFailure,pendingFinancialOperations:0,simulation:true});
 }
 mayRefresh():boolean{return this.current==="online"||this.current==="degraded";}
 mayDisplayStale():boolean{return true;}
 mayQueueFinancialOperation():false{return false;}
 mayAuthorizeCashHandover():false{return false;}
 mayCommitBalance():false{return false;}
 canAcceptServerResponse():boolean{return this.current==="online";}
 requireOnline():void{if(!this.mayRefresh())throw failure("NETWORK_UNAVAILABLE");}
 events():readonly NetworkEvent[]{return Object.freeze([...this.history]);}
 beforeDeviceSuspend():void{this.current="offline";this.lastVerified=null;}
 afterDeviceResume():void{this.current="connecting";}
 forceNoFinancialQueue():void{this.history.splice(0,this.history.length);}
}
export function denyQueuedPayment(_payload:unknown):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
export function staleDataDisclosure(locale:"en"|"bn",ageSeconds:number):string{
 const age=Math.max(0,Math.trunc(ageSeconds));
 return locale==="bn"?
  `এই তথ্য ${age} সেকেন্ড পুরোনো। কোনো পেমেন্ট অনুমোদন করা যাবে না।`:
  `This sample is ${age} seconds old. It cannot authorize a payment.`;
}
