/** Versioned price-quote validation; a quote is not authority to spend. */
import {failure,invariant} from "./errors.js";
import {record,required,integer,text,literal,mapList,boolean} from "./primitives.js";
import {poisha,feePoisha,safeAdd, type Poisha} from "./money.js";
import {syntheticId,type ActorId} from "./identity.js";
export type QuoteOperation="transfer"|"cash_in"|"cash_out"|"merchant_payment";
export type QuoteStatus="quoted"|"reviewed"|"cancelled"|"expired";
export interface SampleQuote {
 readonly id:ActorId;readonly owner:ActorId;readonly counterpart:ActorId;
 readonly operation:QuoteOperation;readonly principal:Poisha;readonly fee:Poisha;
 readonly total:Poisha;readonly version:string;readonly status:QuoteStatus;
 readonly expiresAt:number;readonly simulation:true;readonly mayExecute:false;
 readonly taxesUnverified:true;
}
export interface NewQuoteInput {
 readonly operation:QuoteOperation;
 readonly counterpart_id:ActorId;
 readonly principal_poisha:Poisha;
 readonly source_ref:string;
 readonly lifetime_seconds:number;
}
export function parseOperation(value:unknown):QuoteOperation {
 return literal(value,["transfer","cash_in","cash_out","merchant_payment"] as const);
}
export function parseQuote(value:unknown):SampleQuote {
 const o=record(value);
 invariant(o["simulation"]===true&&o["can_execute"]===false&&o["real_money"]===false,"UNSAFE_CAPABILITY");
 invariant(o["tax_unverified"]===true,"UNSAFE_CAPABILITY");
 const principal=poisha(required(o,"principal_poisha"));
 const fee=feePoisha(required(o,"fee_poisha"));
 const total=poisha(required(o,"total_poisha"));
 invariant(total===safeAdd(principal,fee),"INVALID_MONEY");
 const status=literal(required(o,"status"),["quoted","reviewed","cancelled","expired"] as const);
 return Object.freeze({id:syntheticId(required(o,"quote_id")),owner:syntheticId(required(o,"owner_id")),
  counterpart:syntheticId(required(o,"counterpart_id")),operation:parseOperation(required(o,"operation")),
  principal,fee,total,version:text(required(o,"version"),1,50),status,
  expiresAt:integer(required(o,"expires_at"),1,4_102_444_800),simulation:true,mayExecute:false,taxesUnverified:true});
}
export function parseQuoteList(value:unknown):readonly SampleQuote[]{
 const o=record(value);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(o,"items"),parseQuote,100);
}
export function validateNewQuoteInput(value:NewQuoteInput):NewQuoteInput {
 parseOperation(value.operation);
 syntheticId(value.counterpart_id);
 poisha(value.principal_poisha);
 if(!/^[a-z][A-Za-z0-9_:.\-]{7,96}$/.test(value.source_ref))throw failure("INVALID_INPUT");
 integer(value.lifetime_seconds,30,600);
 return Object.freeze({...value});
}
export function quoteCanBeReviewed(value:SampleQuote,viewer:ActorId,nowSeconds:number):boolean {
 return value.status==="quoted" && value.owner===viewer && value.expiresAt>nowSeconds;
}
export function quoteCanBeCancelled(value:SampleQuote,viewer:ActorId):boolean {
 return value.owner===viewer && value.status==="quoted";
}
export function quoteIsFinal(value:SampleQuote):boolean {
 return value.status==="reviewed"||value.status==="expired"||value.status==="cancelled";
}
export function requireFreshQuote(value:SampleQuote,viewer:ActorId,nowSeconds:number):void {
 if(value.owner!==viewer)throw failure("ROLE_FORBIDDEN");
 if(value.status!=="quoted")throw failure("REQUEST_FINAL");
 if(value.expiresAt<=nowSeconds)throw failure("QUOTE_EXPIRED");
}
export function quoteDisclosure(value:SampleQuote,locale:"en"|"bn"):readonly string[]{
 const en=["SAMPLE QUOTE ONLY — NO MONEY MOVED","Fee is an unapproved pilot assumption",
   "Applicable taxes have not been verified","This review cannot authorize a payment"];
 const bn=["শুধু নমুনা হিসাব — কোনো অর্থ স্থানান্তর হয়নি","ফি অনুমোদিত নয়, পরীক্ষামূলক ধারণা",
   "প্রযোজ্য কর যাচাই করা হয়নি","পর্যালোচনা কোনো পেমেন্ট অনুমোদন করে না"];
 void value;
 return Object.freeze(locale==="bn"?bn:en);
}
export interface QuoteComparison {readonly sameIdentity:boolean;readonly samePrice:boolean;
 readonly sameRevision:boolean;readonly requiresNewReview:boolean;}
export function compareQuotes(before:SampleQuote,after:SampleQuote):QuoteComparison {
 const sameIdentity=before.id===after.id&&before.owner===after.owner&&before.counterpart===after.counterpart;
 const samePrice=before.principal===after.principal&&before.fee===after.fee&&before.total===after.total;
 const sameRevision=before.version===after.version;
 return Object.freeze({sameIdentity,samePrice,sameRevision,
  requiresNewReview:!(sameIdentity&&samePrice&&sameRevision)});
}
export function quoteForRole(value:SampleQuote,actor:ActorId,role:"customer"|"agent"|"merchant"|"operator"):SampleQuote {
 if(value.owner!==actor)throw failure("ROLE_FORBIDDEN");
 if(value.operation==="cash_in"&&role!=="agent")throw failure("ROLE_FORBIDDEN");
 if(value.operation!=="cash_in"&&role!=="customer")throw failure("ROLE_FORBIDDEN");
 return value;
}
export function cannotPostQuote(_quote:SampleQuote):never {throw failure("SERVER_AUTHORITY_ABSENT");}
export function quoteAsReadOnlyMetadata(value:SampleQuote):Readonly<Record<string,string|number|boolean>>{
 return Object.freeze({id:value.id,operation:value.operation,status:value.status,
  expiresAt:value.expiresAt,pricingVersion:value.version,simulation:true,canPostMoney:false});
}
