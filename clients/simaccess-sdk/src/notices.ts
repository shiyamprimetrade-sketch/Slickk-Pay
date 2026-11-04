/** Notification previews are not externally delivered payment confirmations. */
import {failure,invariant} from "./errors.js";
import {record,required,text,integer,literal,mapList} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
export type NoticeKind="quote_ready"|"preview_reviewed"|"preview_cancelled"|
 "security_notice"|"support_draft_created"|"cash_checklist_updated";
export type NoticeStatus="pending"|"acknowledged"|"suppressed";
export interface Notice {
 readonly id:ActorId;readonly kind:NoticeKind;readonly content:string;
 readonly createdAt:number;readonly status:NoticeStatus;readonly attempts:number;
 readonly simulation:true;readonly deliveryEnabled:false;
}
export function parseNotice(value:unknown):Notice{
 const o=record(value);
 invariant(o["simulation"]===true&&o["delivery_enabled"]===false,"UNSAFE_CAPABILITY");
 const content=text(required(o,"content"),1,180);
 if(/\b(?:paid|settled|bank credited|cash released)\b/i.test(content))throw failure("UNSAFE_CAPABILITY");
 return Object.freeze({id:syntheticId(required(o,"id")),
  kind:literal(required(o,"kind"),["quote_ready","preview_reviewed","preview_cancelled",
   "security_notice","support_draft_created","cash_checklist_updated"] as const),
  content,createdAt:integer(required(o,"created_at"),1),
  status:literal(required(o,"status"),["pending","acknowledged","suppressed"] as const),
  attempts:integer(required(o,"attempts"),0,5),simulation:true,deliveryEnabled:false});
}
export function parseNotices(raw:unknown):readonly Notice[]{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(o,"items"),parseNotice,100);
}
export function sortNotices(values:readonly Notice[]):readonly Notice[]{
 return Object.freeze([...values].sort((a,b)=>b.createdAt-a.createdAt||b.id.localeCompare(a.id)));
}
export function noticeSummary(value:Notice,locale:"en"|"bn"):string{
 const known={quote_ready:["Quote ready","নমুনা হিসাব তৈরি"],
  preview_reviewed:["Preview reviewed","নমুনা পর্যালোচিত"],
  preview_cancelled:["Preview cancelled","নমুনা বাতিল"],
  security_notice:["Security notice","নিরাপত্তা বার্তা"],
  support_draft_created:["Support draft saved","সহায়তার খসড়া সংরক্ষিত"],
  cash_checklist_updated:["Cash checklist updated","নগদ চেকলিস্ট হালনাগাদ"]} as const;
 return known[value.kind][locale==="bn"?1:0];
}
export function noticeCounts(values:readonly Notice[]):Readonly<{pending:number;acknowledged:number;suppressed:number}>{
 const result={pending:0,acknowledged:0,suppressed:0};
 for(const item of values)result[item.status]++;
 return Object.freeze(result);
}
export function neverBroadcastNotice(_notice:Notice):false{return false;}
