/** Local dispute and support drafts; no customer issue is submitted to an external service. */
import type {ActorId,SupportCase,CaseEvent,Validation,Locale,SyntheticTransaction} from "./types.js";
import {validateSupportForm,issue,ok,invalid} from "./validation.js";
import {safeTransactionDescription} from "./privacy.js";
export class SupportError extends Error{constructor(readonly code:string){super(code);this.name="SupportError";}}
export interface SupportDraft {readonly id:`sim_${string}`;readonly ownerId:ActorId;readonly subject:string;readonly category:SupportCase["category"];readonly description:string;readonly relatedTransactionId:`sim_${string}`|null;readonly updatedAt:string;readonly state:"editing"|"reviewed"|"discarded";readonly simulation:true;readonly serverSubmitted:false;}
export interface SupportSearch {readonly category?:SupportCase["category"]|"all";readonly status?:SupportCase["status"]|"all";readonly search?:string;}
let seq=0;
function makeId():`sim_${string}`{seq=(seq+1)%10_000_000;return `sim_support_draft_${String(seq).padStart(7,"0")}`;}
export function prepareSupportDraft(ownerId:ActorId,input:Record<string,unknown>,now:string,relatedId:`sim_${string}`|null=null):Validation<SupportDraft>{
 if(!ownerId.startsWith("sim_"))return invalid(issue("owner","synthetic","Demo actor required"));
 const valid=validateSupportForm(input);
 if(!valid.ok)return invalid(...valid.issues);
 if(relatedId!==null&&!relatedId.startsWith("sim_"))return invalid(issue("related","synthetic","Only sample transaction references allowed"));
 if(!Number.isFinite(Date.parse(now)))return invalid(issue("updatedAt","clock","Invalid timestamp"));
 return ok(Object.freeze({id:makeId(),ownerId,subject:valid.value.subject,
  category:valid.value.category,description:valid.value.description,relatedTransactionId:relatedId,
  updatedAt:now,state:"editing" as const,simulation:true as const,serverSubmitted:false as const}));
}
export function reviewSupportDraft(draft:SupportDraft,explicitConsent:boolean,now:string):SupportDraft{
 if(draft.state!=="editing")throw new SupportError("DRAFT_LOCKED");
 if(!explicitConsent)throw new SupportError("DEMO_CONSENT_REQUIRED");
 if(!Number.isFinite(Date.parse(now)))throw new SupportError("INVALID_TIMESTAMP");
 return Object.freeze({...draft,state:"reviewed",updatedAt:now});
}
export function discardSupportDraft(draft:SupportDraft,now:string):SupportDraft{
 if(draft.state==="reviewed")throw new SupportError("REVIEWED_DRAFT_RETAINED");
 return Object.freeze({...draft,state:"discarded",updatedAt:now});
}
export function submitSupportTicket(_draft:SupportDraft):never{
 throw new SupportError("NO_AUTHENTICATED_SUPPORT_ENDPOINT");
}
export function supportCaseList(cases:readonly SupportCase[],ownerId:ActorId,filter:SupportSearch={}):readonly SupportCase[]{
 const search=(filter.search??"").trim().toLowerCase();
 if(search.length>100)throw new SupportError("SEARCH_TOO_LONG");
 return Object.freeze(cases.filter(c=>c.ownerId===ownerId&&c.simulation===true)
  .filter(c=>!filter.category||filter.category==="all"||c.category===filter.category)
  .filter(c=>!filter.status||filter.status==="all"||c.status===filter.status)
  .filter(c=>!search||`${c.subject} ${c.description}`.toLowerCase().includes(search))
  .sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)));
}
export function disputeWarning(transaction:SyntheticTransaction):readonly string[]{
 const warnings=["Synthetic payment reference; no actual funds are at risk."];
 if(transaction.state==="review")warnings.push("A fictitious review is open; this is not a real support case.");
 if(transaction.state==="completed")warnings.push("A completed sample transaction is not proof of real settlement.");
 if(transaction.operation==="cash_out")warnings.push("Cash handover requires two-party confirmation in a real service.");
 if(!transaction.simulation)warnings.push("UNVERIFIED_DATA");
 return Object.freeze(warnings);
}
export function suggestSupportCategory(message:string):SupportCase["category"]{
 const s=message.toLowerCase();
 if(/(?:pin|otp|fraud|password|locked|hacked|security|scam)/.test(s))return "security";
 if(/(?:agent|cash|float|handover)/.test(s))return "agent";
 if(/(?:transaction|transfer|payment|merchant|refund)/.test(s))return "payment";
 return "technical";
}
export function supportSafetyWarnings(input:string):readonly string[]{
 const warnings:string[]=[];
 if(/\b\d{16}\b/.test(input))warnings.push("POSSIBLE_CARD_NUMBER");
 if(/(?:pin|otp|password)\s*[:=]\s*\S+/i.test(input))warnings.push("POSSIBLE_CREDENTIAL");
 if(/\+?8801[3-9]\d{8}/.test(input))warnings.push("POSSIBLE_PHONE");
 if(/(?:NID|National ID)\s*[:=]\s*\d+/i.test(input))warnings.push("POSSIBLE_IDENTITY_NUMBER");
 return Object.freeze(warnings);
}
export function caseTimeline(item:SupportCase):readonly CaseEvent[]{
 if(!item.simulation)throw new SupportError("NOT_SIMULATED");
 return Object.freeze([...item.history].sort((a,b)=>a.at.localeCompare(b.at)));
}
export function supportStatusCounts(items:readonly SupportCase[]):Readonly<Record<SupportCase["status"],number>>{
 const result:Record<SupportCase["status"],number>={open:0,investigating:0,waiting:0,closed:0};
 for(const x of items){if(!x.simulation)throw new SupportError("INVALID_CASE");result[x.status]++;}
 return Object.freeze(result);
}
export function supportCaseSummary(item:SupportCase,locale:Locale):string{
 const state=locale==="bn"?({open:"খোলা",investigating:"তদন্তাধীন",waiting:"অপেক্ষমান",closed:"বন্ধ"}[item.status]):item.status;
 return `${safeTransactionDescription(item.subject)} · ${state} · DEMO`;
}
export function permittedCaseAction(status:SupportCase["status"],action:"reopen"|"reply"|"close"):boolean{
 if(status==="closed")return action==="reopen";
 if(status==="investigating"||status==="waiting")return action==="reply"||action==="close";
 return action==="reply"||action==="close";
}
export function createOfflineCaseEvent(caseItem:SupportCase,action:string,now:string):{saved:false;reason:string;preview:CaseEvent}{
 if(caseItem.simulation!==true||!Number.isFinite(Date.parse(now)))throw new SupportError("INVALID_SAMPLE_CASE");
 return {saved:false,reason:"NO_SUPPORT_WRITE_API",preview:{at:now,action,detail:"Draft event only"}};
}
export function supportNextSteps(caseItem:SupportCase):readonly string[]{
 const steps:string[]=[];
 if(caseItem.status==="open")steps.push("Review fictional record and classify the concern.");
 if(caseItem.status==="investigating")steps.push("Never demand customer PIN or OTP during investigation.");
 if(caseItem.status==="waiting")steps.push("No payment should be retried without authoritative status.");
 if(caseItem.status==="closed")steps.push("Closure in this fixture does not confirm compensation.");
 steps.push("For real complaints, contact the licensed service provider.");
 return Object.freeze(steps);
}
