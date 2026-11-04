/** Deterministic connection circuit breaker for a local, nonfinancial API. */
import {failure,invariant} from "./errors.js";
export type CircuitState="closed"|"open"|"half_open";
export interface CircuitSnapshot {
 readonly state:CircuitState;readonly failures:number;
 readonly openedAt:number|null;readonly lastFailureAt:number|null;
 readonly allowFinancialMutations:false;readonly simulation:true;
}
export class ConnectionCircuit {
 private failures=0;
 private openedAt:number|null=null;
 private lastFailureAt:number|null=null;
 private stateValue:CircuitState="closed";
 constructor(private readonly now:()=>number=()=>Date.now(),
  private readonly threshold=3,private readonly coolOffMs=10000){
  if(!Number.isSafeInteger(threshold)||threshold<1||threshold>10)throw failure("INVALID_INPUT");
  if(!Number.isSafeInteger(coolOffMs)||coolOffMs<1000||coolOffMs>600000)throw failure("INVALID_INPUT");
 }
 maySendRead():boolean{
  if(this.stateValue==="closed")return true;
  if(this.stateValue==="open"&&this.openedAt!==null&&this.now()-this.openedAt>=this.coolOffMs){
   this.stateValue="half_open";return true;
  }
  return this.stateValue==="half_open";
 }
 beforeRead():void{if(!this.maySendRead())throw failure("NETWORK_UNAVAILABLE");}
 success():CircuitSnapshot{
  this.failures=0;this.openedAt=null;this.lastFailureAt=null;this.stateValue="closed";
  return this.snapshot();
 }
 failure():CircuitSnapshot{
  this.lastFailureAt=this.now();this.failures++;
  if(this.failures>=this.threshold){this.openedAt=this.now();this.stateValue="open";}
  return this.snapshot();
 }
 snapshot():CircuitSnapshot{
  return Object.freeze({state:this.stateValue,failures:this.failures,openedAt:this.openedAt,
   lastFailureAt:this.lastFailureAt,allowFinancialMutations:false,simulation:true});
 }
 resetAfterNetworkChange():void{
  this.failures=0;this.openedAt=null;this.stateValue="half_open";
 }
 mayRetryPost():false{return false;}
 forceMoneyDenial():never{throw failure("SERVER_AUTHORITY_ABSENT");}
}
