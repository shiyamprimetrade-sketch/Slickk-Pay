/** Durable preview state, explicitly disconnected from the financial ledger. */
import {failure,invariant} from "./errors.js";
import {record,required,integer,literal,mapList} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
import {parseOperation,type QuoteOperation, type SampleQuote} from "./quotes.js";
export type ReviewStatus="reviewed"|"cancelled"|"expired";
export interface ReviewedPreview {
 readonly id:ActorId;readonly owner:ActorId;readonly quoteId:ActorId;
 readonly operation:QuoteOperation;readonly status:ReviewStatus;readonly acceptedAt:number;
 readonly updatedAt:number;readonly revision:number;readonly simulation:true;
 readonly financialPosting:false;readonly handoverAuthorized:false;
}
export function parseReview(value:unknown):ReviewedPreview {
 const o=record(value);
 invariant(o["simulation"]===true && o["financial_posting"]===false &&
  o["handover_authorized"]===false,"UNSAFE_CAPABILITY");
 const status=literal(required(o,"status"),["reviewed","cancelled","expired"] as const);
 return Object.freeze({id:syntheticId(required(o,"request_id")),
  owner:syntheticId(required(o,"owner_id")),quoteId:syntheticId(required(o,"quote_id")),
  operation:parseOperation(required(o,"operation")),status,
  acceptedAt:integer(required(o,"accepted_at"),1),updatedAt:integer(required(o,"updated_at"),1),
  revision:integer(required(o,"revision"),1),simulation:true,financialPosting:false,handoverAuthorized:false});
}
export function parseRequestList(value:unknown):readonly ReviewedPreview[]{
 const o=record(value);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(o,"items"),parseReview,100);
}
export function requireOwnedReview(review:ReviewedPreview,actor:ActorId):void{
 if(review.owner!==actor)throw failure("ROLE_FORBIDDEN");
}
export function requestIsClosed(value:ReviewedPreview):boolean{
 return value.status==="cancelled"||value.status==="expired";
}
export function neverResumeCancelled(previous:ReviewedPreview,next:ReviewedPreview):void{
 if(previous.id!==next.id||previous.quoteId!==next.quoteId)throw failure("CONFLICT");
 if(next.revision<previous.revision)throw failure("UNTRUSTED_RESPONSE");
 if(previous.status==="cancelled"&&next.status!=="cancelled")throw failure("REQUEST_FINAL");
 if(previous.status==="expired"&&next.status!=="expired")throw failure("REQUEST_FINAL");
}
export function assertReviewMatchesQuote(review:ReviewedPreview,quote:SampleQuote):void{
 invariant(review.owner===quote.owner&&review.quoteId===quote.id,"UNTRUSTED_RESPONSE");
 invariant(review.operation===quote.operation,"UNTRUSTED_RESPONSE");
 invariant(review.simulation===true && quote.simulation===true,"UNSAFE_CAPABILITY");
}
export interface ReviewTimelineItem {
 readonly id:string;readonly kind:string;readonly at:number;
 readonly digest:string;readonly summary:string;readonly simulation:true;
}
export function parseTimelineItem(value:unknown):ReviewTimelineItem{
 const o=record(value);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 const id=syntheticId(required(o,"id"));
 const kind=String(required(o,"kind"));
 if(!/^[a-z_]{3,40}$/.test(kind))throw failure("UNTRUSTED_RESPONSE");
 const digest=String(required(o,"digest"));
 if(!/^[a-f0-9]{64}$/.test(digest))throw failure("UNTRUSTED_RESPONSE");
 const summary=String(required(o,"summary"));
 if(summary.length>120||/[<>\r\n]/.test(summary))throw failure("UNTRUSTED_RESPONSE");
 return Object.freeze({id,kind,at:integer(required(o,"at"),1),digest,summary,simulation:true});
}
export function timelineChronological(values:readonly ReviewTimelineItem[]):boolean{
 return values.every((item,index)=>index===0||item.at >= (values[index-1]?.at??0));
}
export function timelineHasCancellation(values:readonly ReviewTimelineItem[]):boolean{
 return values.some(item=>item.kind==="preview_cancelled");
}
export interface RequestViewModel {readonly statusText:string;readonly canCancel:boolean;
 readonly paymentStatus:"NOT_A_PAYMENT";readonly handoverStatus:"NOT_AUTHORIZED";}
export function requestView(review:ReviewedPreview,viewer:ActorId,locale:"en"|"bn"):RequestViewModel{
 requireOwnedReview(review,viewer);
 return Object.freeze({
  statusText:locale==="bn"?(review.status==="reviewed"?"শুধু পর্যালোচিত":review.status==="cancelled"?"বাতিল":"মেয়াদ শেষ"):
    (review.status==="reviewed"?"Reviewed, not paid":review.status==="cancelled"?"Cancelled":"Expired"),
  canCancel:review.status==="reviewed",paymentStatus:"NOT_A_PAYMENT",handoverStatus:"NOT_AUTHORIZED"
 });
}
export function preventLocalReviewPosting(_request:ReviewedPreview):never{throw failure("SERVER_AUTHORITY_ABSENT");}
