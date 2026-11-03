/** Financial activity is derived from fixtures, never implied to be a reconciled statement. */
import type {SyntheticTransaction,Operation,Status,Locale,ActorId} from "./types.js";
import {formatBDT,assertPoisha} from "./money.js";
import {operationLabel,statusLabel,localTime} from "./locales.js";
import {maskIdentifier,safeTransactionDescription} from "./privacy.js";
export interface ActivityFilter {
 readonly operation?:Operation|"all";
 readonly status?:Status|"all";
 readonly from?:string;
 readonly to?:string;
 readonly search?:string;
 readonly page?:number;
 readonly pageSize?:number;
}
export interface ActivityPage {readonly rows:readonly SyntheticTransaction[];readonly page:number;readonly pageSize:number;readonly total:number;readonly pageCount:number;readonly simulation:true;}
export interface ActivityTotals {readonly count:number;readonly successful:number;readonly failed:number;readonly review:number;readonly sampleValuePoisha:number;readonly sampleFeesPoisha:number;readonly simulation:true;}
function validDate(value:string):boolean{
 const ms=Date.parse(value);
 return Number.isFinite(ms)&&/^[0-9]{4}-[0-9]{2}-[0-9]{2}/.test(value);
}
function boundedInt(value:number|undefined,fallback:number,max:number):number{
 const result=value??fallback;
 if(!Number.isSafeInteger(result)||result<1||result>max)throw new Error("INVALID_PAGE");
 return result;
}
export function activityPage(records:readonly SyntheticTransaction[],actorId:ActorId,filter:ActivityFilter={}):ActivityPage{
 if(!actorId.startsWith("sim_"))throw new Error("INVALID_ACTOR");
 const page=boundedInt(filter.page,1,100_000),pageSize=boundedInt(filter.pageSize,20,100);
 if(filter.from&&!validDate(filter.from))throw new Error("INVALID_FROM_DATE");
 if(filter.to&&!validDate(filter.to))throw new Error("INVALID_TO_DATE");
 if(filter.from&&filter.to&&filter.from>filter.to)throw new Error("REVERSED_DATE_RANGE");
 const search=(filter.search??"").trim().toLocaleLowerCase("en");
 if(search.length>80)throw new Error("SEARCH_TOO_LONG");
 const selected=records.filter(x=>{
  if(x.ownerId!==actorId||!x.simulation||x.dataProvenance!=="fixture")return false;
  if(filter.operation&&filter.operation!=="all"&&x.operation!==filter.operation)return false;
  if(filter.status&&filter.status!=="all"&&x.state!==filter.status)return false;
  if(filter.from&&x.occurredAt.slice(0,10)<filter.from.slice(0,10))return false;
  if(filter.to&&x.occurredAt.slice(0,10)>filter.to.slice(0,10))return false;
  if(search&&!`${x.otherParty} ${x.description} ${x.reference}`.toLocaleLowerCase("en").includes(search))return false;
  return true;
 }).sort((a,b)=>b.occurredAt.localeCompare(a.occurredAt)||a.id.localeCompare(b.id));
 const first=(page-1)*pageSize;
 return Object.freeze({rows:Object.freeze(selected.slice(first,first+pageSize)),page,pageSize,
  total:selected.length,pageCount:Math.ceil(selected.length/pageSize),simulation:true});
}
export function aggregateActivity(records:readonly SyntheticTransaction[]):ActivityTotals{
 let count=0,successful=0,failed=0,review=0,value=0,fees=0;
 for(const tx of records){
  if(!tx.simulation)throw new Error("NON_SYNTHETIC_ACTIVITY");
  count++;
  if(tx.state==="completed"){
   successful++;value+=assertPoisha(tx.amountPoisha);fees+=assertPoisha(tx.feePoisha);
  }
  if(tx.state==="failed")failed++;
  if(tx.state==="review")review++;
 }
 if(!Number.isSafeInteger(value)||!Number.isSafeInteger(fees))throw new Error("TOTAL_OVERFLOW");
 return Object.freeze({count,successful,failed,review,sampleValuePoisha:value,sampleFeesPoisha:fees,simulation:true});
}
export interface ActivityRowModel {readonly reference:string;readonly heading:string;readonly subheading:string;readonly amount:string;readonly fee:string;readonly status:string;readonly badge:"positive"|"warning"|"danger"|"neutral";readonly simulation:true;}
export function activityRowModel(tx:SyntheticTransaction,locale:Locale):ActivityRowModel{
 const colors:Record<Status,ActivityRowModel["badge"]>={completed:"positive",review:"warning",failed:"danger",cancelled:"neutral",pending:"neutral"};
 return Object.freeze({reference:maskIdentifier(tx.reference),heading:operationLabel(locale,tx.operation),
  subheading:`${safeTransactionDescription(tx.otherParty)} · ${localTime(locale,tx.occurredAt)}`,
  amount:formatBDT(tx.amountPoisha,locale),fee:formatBDT(tx.feePoisha,locale),
  status:statusLabel(locale,tx.state),badge:colors[tx.state],simulation:true});
}
export function groupActivityByDay(records:readonly SyntheticTransaction[]):Readonly<Record<string,readonly SyntheticTransaction[]>>{
 const groups=new Map<string,SyntheticTransaction[]>();
 for(const tx of records){
  if(!validDate(tx.occurredAt))throw new Error("INVALID_ACTIVITY_TIMESTAMP");
  const key=tx.occurredAt.slice(0,10);
  groups.set(key,[...(groups.get(key)??[]),tx]);
 }
 const result:Record<string,readonly SyntheticTransaction[]>={};
 for(const [key,items] of [...groups.entries()].sort(([a],[b])=>b.localeCompare(a))){
  result[key]=Object.freeze([...items].sort((a,b)=>b.occurredAt.localeCompare(a.occurredAt)));
 }
 return Object.freeze(result);
}
export function operationDistribution(records:readonly SyntheticTransaction[]):Readonly<Record<Operation,number>>{
 const data:Record<Operation,number>={transfer:0,cash_in:0,cash_out:0,merchant_payment:0,balance_inquiry:0};
 records.forEach(x=>{if(!x.simulation)throw new Error("NOT_SAMPLE");data[x.operation]++;});
 return Object.freeze(data);
}
export function findActivityByReference(records:readonly SyntheticTransaction[],owner:ActorId,ref:string):SyntheticTransaction|null{
 return records.find(t=>t.ownerId===owner&&t.reference===ref&&t.simulation)??null;
}
export function activityTimeline(records:readonly SyntheticTransaction[],limit=30):readonly {id:string;time:string;label:string;status:string}[]{
 if(!Number.isSafeInteger(limit)||limit<1||limit>100)throw new Error("INVALID_LIMIT");
 return Object.freeze([...records].sort((a,b)=>b.occurredAt.localeCompare(a.occurredAt)).slice(0,limit)
  .map(x=>({id:x.id,time:x.occurredAt,label:`${x.operation} ${x.amountPoisha} poisha`,status:x.state})));
}
export function detectActivityAnomalies(records:readonly SyntheticTransaction[]):readonly string[]{
 const issues:string[]=[];
 const keys=new Set<string>();
 for(const tx of records){
  if(!tx.id.startsWith("sim_")||!tx.reference.startsWith("sim_")||!tx.simulation)issues.push("UNTRUSTED_RECORD");
  if(keys.has(tx.reference))issues.push("DUPLICATE_REFERENCE");
  keys.add(tx.reference);
  if(!Number.isSafeInteger(tx.amountPoisha)||tx.amountPoisha<0)issues.push("INVALID_AMOUNT");
  if(!validDate(tx.occurredAt))issues.push("INVALID_TIMESTAMP");
 }
 return Object.freeze([...new Set(issues)]);
}
export function activityFooter(locale:Locale,records:readonly SyntheticTransaction[]):string{
 const n=records.length;
 return locale==="bn"?`${n}টি কাল্পনিক লেনদেন — ব্যাংক বিবরণী নয়`:`${n} fictional records — not a bank statement`;
}
