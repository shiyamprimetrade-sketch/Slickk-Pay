/** Structured audit proof metadata. Never trust HTTP text as a verified journal. */
import {failure,invariant} from "./errors.js";
import {record,required,integer,hex,text,mapList} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
export interface AuditCheckpoint {
 readonly sequence:number;readonly digest:string;
 readonly valid:boolean;readonly simulation:true;
 readonly externalSettlementVerified:false;
}
export interface AuditEvent {
 readonly id:ActorId;readonly actor:ActorId;
 readonly kind:string;readonly at:number;readonly digest:string;
 readonly previousDigest:string;readonly simulation:true;
}
export function parseAuditCheckpoint(raw:unknown):AuditCheckpoint{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 invariant(o["real_settlement_verified"]!==true,"UNSAFE_CAPABILITY");
 return Object.freeze({sequence:integer(required(o,"checked")??required(o,"sequence"),0),
  digest:hex(o["latest_hash"]??o["digest"],64),valid:o["valid"]===true,
  simulation:true,externalSettlementVerified:false});
}
export function parseAuditEvent(raw:unknown):AuditEvent{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 const kind=text(required(o,"kind"),2,64);
 if(!/^[a-z_]+$/.test(kind))throw failure("UNTRUSTED_RESPONSE");
 return Object.freeze({id:syntheticId(required(o,"event_id")),
  actor:syntheticId(required(o,"actor_id")),kind,at:integer(required(o,"at"),1),
  digest:hex(required(o,"digest")),previousDigest:hex(required(o,"previous_digest")),
  simulation:true});
}
export function parseAuditEvents(raw:unknown):readonly AuditEvent[]{
 const obj=record(raw);
 invariant(obj["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(obj,"events"),parseAuditEvent,250);
}
export function verifyEventOrdering(events:readonly AuditEvent[],genesis="0".repeat(64)):boolean{
 let previous=genesis;
 for(const event of events){
  if(event.previousDigest!==previous)return false;
  previous=event.digest;
 }
 return true;
}
export interface AuditDisclosure {
 readonly checkedEvents:number;readonly claim:string;
 readonly verifiedByClient:false;readonly authenticBankProof:false;
}
export function auditDisclosure(checkpoint:AuditCheckpoint):AuditDisclosure{
 return Object.freeze({checkedEvents:checkpoint.sequence,
  claim:checkpoint.valid?"Lab database reported internal chain consistency":"Lab reported inconsistent audit evidence",
  verifiedByClient:false,authenticBankProof:false});
}
export function doNotTrustRemoteChain(_proof:AuditCheckpoint):false{return false;}
export function verifyNoCounterfeitSettlement(raw:unknown):void{
 const o=record(raw);
 if(o["settled"]===true||o["bank_confirmed"]===true||o["revenue_real"]===true)
  throw failure("UNSAFE_CAPABILITY");
}
