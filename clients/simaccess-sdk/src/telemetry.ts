/** Privacy-safe operational diagnostics; no transaction or authorization secrets. */
import {failure,invariant} from "./errors.js";
import {text,integer} from "./primitives.js";
import type {RequestAudit} from "./transport.js";
export type TelemetryKind="network_request"|"session_transition"|"response_rejected"|
 "preview_reviewed"|"offline_detected"|"client_locked";
export interface TelemetryRow {
 readonly id:number;readonly kind:TelemetryKind;readonly at:number;
 readonly durationMs:number;readonly status:string;
 readonly simulation:true;readonly containsPersonalData:false;
}
export interface TelemetrySummary {
 readonly total:number;readonly failed:number;readonly p95LatencyMs:number;
 readonly lastEventAt:number|null;readonly simulation:true;
 readonly realTransactionCount:0;
}
export class TelemetryDesk {
 private readonly rows:TelemetryRow[]=[];
 private serial=0;
 constructor(private readonly now:()=>number=()=>Date.now(),private readonly limit=200){
  integer(limit,1,2000);
 }
 append(kind:TelemetryKind,status:string,durationMs=0):TelemetryRow{
  text(status,1,40);
  integer(durationMs,0,120000);
  const row=Object.freeze({id:++this.serial,kind,at:this.now(),durationMs,status,
   simulation:true as const,containsPersonalData:false as const});
  this.rows.push(row);
  if(this.rows.length>this.limit)this.rows.shift();
  return row;
 }
 receiveRequestAudit(event:RequestAudit):TelemetryRow{
  invariant(event.simulation===true);
  return this.append("network_request",event.status,event.elapsedMs);
 }
 entries():readonly TelemetryRow[]{return Object.freeze([...this.rows]);}
 summary():TelemetrySummary{
  const latency=this.rows.map(x=>x.durationMs).sort((a,b)=>a-b);
  const i=Math.max(0,Math.ceil(latency.length*0.95)-1);
  return Object.freeze({total:this.rows.length,
   failed:this.rows.filter(x=>/fail|error|reject|offline/i.test(x.status)).length,
   p95LatencyMs:latency[i]??0,lastEventAt:this.rows[this.rows.length-1]?.at??null,
   simulation:true,realTransactionCount:0});
 }
 clear():void{this.rows.length=0;}
 serializeSafe():string{
  return JSON.stringify({rows:this.rows,summary:this.summary(),simulation:true},null,2);
 }
 mayLogRequestBodies():false{return false;}
 mayLogBearerTokens():false{return false;}
 reportPaymentSuccess():never{throw failure("SERVER_AUTHORITY_ABSENT");}
}
export function privacyLintTelemetry(line:string):boolean{
 if(/(?:authorization|bearer|token|secret|password|otp|pin)\s*[:=]/i.test(line))return false;
 if(/\b01[3-9]\d{8}\b/.test(line))return false;
 return true;
}
