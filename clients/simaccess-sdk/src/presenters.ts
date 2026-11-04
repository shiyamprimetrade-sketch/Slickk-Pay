/** Bilingual read-only projection functions for low-end Android UI. */
import {feePoisha,moneyLabel,type Poisha} from "./money.js";
import type {SampleQuote} from "./quotes.js";
import type {ReviewedPreview} from "./requests.js";
import type {CashDialogue,CashChecklist} from "./cash.js";
import type {AgentPreview} from "./directory.js";
import type {Notice} from "./notices.js";
import type {PreviewReceipt} from "./receipts.js";
export type Locale="en"|"bn";
export interface DisplayRow {readonly label:string;readonly value:string;
 readonly important:boolean;readonly simulation:true;}
export interface DisplayCard {readonly title:string;readonly subtitle:string;
 readonly rows:readonly DisplayRow[];readonly warning:string;
 readonly canSubmitMoney:false;readonly simulation:true;}
function row(label:string,value:string,important=false):DisplayRow{
 return Object.freeze({label,value,important,simulation:true});
}
export function quoteCard(quote:SampleQuote,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:bn?"নমুনা মূল্য হিসাব":"Sample fee quote",
  subtitle:bn?"এই তথ্য কোনো অর্থ লেনদেন নয়":"No money has been moved",
  rows:Object.freeze([
   row(bn?"মূল অর্থ":"Principal",moneyLabel(quote.principal,locale)),
   row(bn?"প্রস্তাবিত ফি":"Proposed fee",moneyLabel(quote.fee,locale)),
   row(bn?"মোট":"Preview total",moneyLabel(quote.total,locale),true),
   row(bn?"অবস্থা":"Review state",quote.status),
   row(bn?"দর সংস্করণ":"Rate version",quote.version)
  ]),warning:bn?"ফি ও কর এখনো অনুমোদিত নয়":"Pilot pricing and taxes are unverified",
  canSubmitMoney:false,simulation:true});
}
export function requestCard(request:ReviewedPreview,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:bn?"শুধু নমুনা পর্যালোচনা":"Preview request only",
  subtitle:bn?"ব্যাংক বা এজেন্টে কোনো অর্থ যায়নি":"No bank or agent money movement",
  rows:Object.freeze([
   row(bn?"অনুরোধ":"Request",request.id),
   row(bn?"ধরন":"Kind",request.operation),
   row(bn?"অবস্থা":"State",request.status,true),
   row(bn?"সংস্করণ":"Revision",String(request.revision))
  ]),warning:bn?"নগদ হস্তান্তর অনুমোদিত নয়":"Cash handover not authorized",
  canSubmitMoney:false,simulation:true});
}
export function cashReviewCard(dialogue:CashDialogue,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 const reviewed=Number(dialogue.customerReviewed)+Number(dialogue.agentReviewed);
 return Object.freeze({title:bn?"দুই পক্ষের নমুনা পর্যালোচনা":"Two-party sample review",
  subtitle:bn?"পর্যালোচনা কোনো অর্থ প্রদান নয়":"Acknowledgements are not payment confirmation",
  rows:Object.freeze([
   row(bn?"গ্রাহক":"Customer",dialogue.customerReviewed?"✓":"—"),
   row(bn?"এজেন্ট":"Agent",dialogue.agentReviewed?"✓":"—"),
   row(bn?"পর্যালোচনা":"Reviews",`${reviewed}/2`,true),
   row(bn?"অবস্থা":"State",dialogue.state)
  ]),warning:bn?"কোনো নগদ হস্তান্তর করবেন না":"Do not hand over cash",
  canSubmitMoney:false,simulation:true});
}
export function cashChecklistCard(checklist:CashChecklist,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:bn?"এজেন্ট চেকলিস্ট":"Agent sample checklist",
  subtitle:bn?"নগদ প্রাপ্যতা পরীক্ষামূলক":"Fictional cash availability",
  rows:Object.freeze([
   row(bn?"নমুনা নগদ":"Sample cash",checklist.sampleCashAvailable?"yes":"no"),
   row(bn?"গ্রাহক উপস্থিত":"Customer present",checklist.sampleCustomerPresent?"yes":"no"),
   row(bn?"সতর্কতা পড়েছেন":"Warnings acknowledged",checklist.warningsRead?"yes":"no")
  ]),warning:bn?"চেকলিস্ট সম্পূর্ণ হলেও লেনদেন নয়":"Checklist completion cannot transfer funds",
  canSubmitMoney:false,simulation:true});
}
export function agentCard(agent:AgentPreview,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:agent.label,subtitle:bn?"কাল্পনিক এজেন্ট":"Synthetic agent fixture",
  rows:Object.freeze([
   row(bn?"অঞ্চল":"Sample region",agent.region),
   row(bn?"নমুনা নগদ":"Sample cash",moneyLabel(agent.sampleCash,locale)),
   row(bn?"নমুনা ফ্লোট":"Sample float",moneyLabel(agent.sampleFloat,locale))
  ]),warning:bn?"বাস্তব এজেন্ট বা অবস্থান যাচাই করা হয়নি":"No real agent or location verification",
  canSubmitMoney:false,simulation:true});
}
export function noticeCard(notice:Notice,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:bn?"ডেমো বার্তা":"Demo notification",subtitle:notice.kind,
  rows:Object.freeze([row(bn?"বিবরণ":"Content",notice.content),
   row(bn?"অবস্থা":"Status",notice.status)]),
  warning:bn?"কোনো বাস্তব নোটিফিকেশন পাঠানো হয়নি":"No external notification delivered",
  canSubmitMoney:false,simulation:true});
}
export function receiptCard(receipt:PreviewReceipt,locale:Locale):DisplayCard{
 const bn=locale==="bn";
 return Object.freeze({title:receipt.watermark,
  subtitle:bn?"পেমেন্টের প্রমাণ নয়":"Not payment proof",
  rows:Object.freeze(receipt.lines.map(x=>row(x.label,x.value))),
  warning:bn?"এটি ব্যাংক সেটেলমেন্ট রসিদ নয়":"This is not a bank settlement receipt",
  canSubmitMoney:false,simulation:true});
}
export function emptyStateCard(locale:Locale):DisplayCard{
 return Object.freeze({title:locale==="bn"?"নমুনা তথ্য নেই":"No sample records",
  subtitle:locale==="bn"?"শুধু পড়ার ব্যবস্থা":"Read-only lab",
  rows:Object.freeze([]),warning:locale==="bn"?"কোনো পেমেন্ট হয়নি":"No payment occurred",
  canSubmitMoney:false,simulation:true});
}
