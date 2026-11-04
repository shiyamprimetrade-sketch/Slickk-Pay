/** Owner-scoped synthetic activity. No row asserts payment settlement. */
import {failure,invariant} from "./errors.js";
import {record,required,integer,literal,mapList,text} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
import {feePoisha,type Poisha} from "./money.js";
export type SampleDirection="in"|"out"|"none";
export type SampleEventStatus="pending"|"reviewed"|"cancelled"|"expired"|"sample";
export interface ActivityRow {
 readonly id:ActorId;readonly actor:ActorId;
 readonly label:string;readonly direction:SampleDirection;
 readonly status:SampleEventStatus;readonly amount:Poisha;
 readonly occurredAt:number;readonly simulation:true;
 readonly settled:false;
}
export function parseActivity(row:unknown,owner:ActorId):ActivityRow{
 const o=record(row);
 invariant(o["simulation"]!==false && o["settled"]!==true &&
  o["payment_proof"]!==true && o["bank_settlement"]!==true,"UNSAFE_CAPABILITY");
 const actor=syntheticId(o["actor_id"]??o["owner_id"]??owner);
 if(actor!==owner)throw failure("ROLE_FORBIDDEN");
 const serverStatus=o["status"];
 const normalized=serverStatus==="sample_paid"?"sample":serverStatus==="sample_pending"?"pending":
  serverStatus==="sample_cancelled"?"cancelled":serverStatus??"sample";
 const status=literal(normalized,["pending","reviewed","cancelled","expired","sample"] as const);
 const direction=literal(o["direction"]??"none",["in","out","none"] as const);
 return Object.freeze({
  id:syntheticId(o["event_id"]??o["id"]),actor,
  label:text(o["description"]??o["label"]??"Sample activity",1,120),direction,status,
  amount:feePoisha(o["amount_poisha"]??o["poisha"]??0),occurredAt:integer(o["at"]??o["occurred_at"]??o["created_at"]??1,1),
  simulation:true,settled:false
 });
}
export function parseActivityPage(raw:unknown,owner:ActorId):readonly ActivityRow[]{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 const values=o["rows"]??o["items"];
 return mapList(values,item=>parseActivity(item,owner),250);
}
export interface ActivityQuery {
 readonly limit:number;
 readonly direction?:SampleDirection;
 readonly status?:"sample_paid"|"sample_cancelled"|"sample_pending";
}
export function queryActivity(query:ActivityQuery):Readonly<Record<string,string|number>>{
 const limit=integer(query.limit,1,250);
 const result:Record<string,string|number>={limit};
 if(query.direction)result["direction"]=literal(query.direction,["in","out","none"] as const);
 if(query.status)result["status"]=literal(query.status,["sample_paid","sample_cancelled","sample_pending"] as const);
 return Object.freeze(result);
}
export function latestActivity(rows:readonly ActivityRow[],limit=20):readonly ActivityRow[]{
 integer(limit,1,250);
 return Object.freeze([...rows].sort((a,b)=>b.occurredAt-a.occurredAt||b.id.localeCompare(a.id)).slice(0,limit));
}
export function directionTotals(rows:readonly ActivityRow[]):Readonly<{incoming:Poisha;outgoing:Poisha;unsettled:number}>{
 let incoming=0,outgoing=0,unsettled=0;
 for(const row of rows){
  if(row.direction==="in")incoming+=row.amount;
  if(row.direction==="out")outgoing+=row.amount;
  if(!row.settled)unsettled++;
 }
 invariant(Number.isSafeInteger(incoming)&&Number.isSafeInteger(outgoing),"INVALID_MONEY");
 return Object.freeze({incoming:feePoisha(incoming),outgoing:feePoisha(outgoing),unsettled});
}
export function redactActivity(row:ActivityRow):Readonly<Record<string,string|number|boolean>>{
 return Object.freeze({id:row.id,direction:row.direction,status:row.status,
  amountPoisha:row.amount,simulation:true,settlementVerified:false});
}
export function ensureNoLiveHistory(rows:readonly ActivityRow[]):void{
 if(rows.some(x=>x.settled||x.simulation!==true))throw failure("UNSAFE_CAPABILITY");
}
export function sampleActivityLabel(status:SampleEventStatus,locale:"en"|"bn"):string{
 const en={pending:"Pending demo",reviewed:"Reviewed preview",cancelled:"Cancelled preview",expired:"Expired preview",sample:"Fictional event"};
 const bn={pending:"ডেমো অপেক্ষমাণ",reviewed:"পর্যালোচনা সম্পন্ন",cancelled:"বাতিল নমুনা",expired:"মেয়াদোত্তীর্ণ",sample:"কাল্পনিক ঘটনা"};
 return (locale==="bn"?bn:en)[status];
}
