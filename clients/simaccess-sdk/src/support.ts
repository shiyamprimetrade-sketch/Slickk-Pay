/** Privacy-aware support case drafts, without external submission. */
import {failure,invariant} from "./errors.js";
import {record,required,text,literal,mapList,integer} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
export type SupportCategory="question"|"privacy"|"incorrect_quote"|"suspected_fraud";
export interface SupportCase {
 readonly id:ActorId;readonly owner:ActorId;readonly category:SupportCategory;
 readonly summary:string;readonly createdAt:number;readonly status:"draft"|"closed";
 readonly simulation:true;readonly externallySubmitted:false;
}
export function redactSupportText(input:string):string{
 let output=text(input,0,500);
 output=output.replace(/\b01[3-9]\d{8}\b/g,"[phone hidden]");
 output=output.replace(/\b\d{13,19}\b/g,"[number hidden]");
 output=output.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,"[email hidden]");
 output=output.replace(/(?:password|pin|otp|cvv)\s*[:=]\s*\S+/gi,"[secret hidden]");
 return output;
}
export function parseSupportCase(raw:unknown,expectedOwner?:ActorId):SupportCase{
 const obj=record(raw);
 invariant(obj["simulation"]===true && obj["externally_submitted"]!==true && obj["submitted_to_provider"]!==true,"UNSAFE_CAPABILITY");
 const summary=redactSupportText(text(obj["description"]??obj["summary"]??"Sample issue",1,500));
 return Object.freeze({id:syntheticId(required(obj,"case_id")),
  owner:syntheticId(obj["owner_id"]??expectedOwner),
  category:literal(required(obj,"category"),["question","privacy","incorrect_quote","suspected_fraud"] as const),
  summary,createdAt:integer(obj["created_at"]??1,1),
  status:literal(obj["status"]??"draft",["draft","closed"] as const),
  simulation:true,externallySubmitted:false});
}
export function parseSupportList(raw:unknown,expectedOwner?:ActorId):readonly SupportCase[]{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(o,"cases"),item=>parseSupportCase(item,expectedOwner),100);
}
export function supportForViewer(cases:readonly SupportCase[],owner:ActorId):readonly SupportCase[]{
 if(cases.some(x=>x.owner!==owner))throw failure("ROLE_FORBIDDEN");
 return Object.freeze([...cases]);
}
export function validateSupportDraft(category:SupportCategory,description:string):Readonly<{category:SupportCategory;description:string}>{
 const c=literal(category,["question","privacy","incorrect_quote","suspected_fraud"] as const);
 const original=text(description,10,500);
 const descriptionSafe=redactSupportText(original);
 if(descriptionSafe.trim().length<10)throw failure("INVALID_INPUT");
 return Object.freeze({category:c,description:descriptionSafe});
}
export function supportSafetyNote(locale:"en"|"bn"):string{
 return locale==="bn"?"এটি ডেমো অভিযোগের খসড়া; কোনো প্রতিষ্ঠানে পাঠানো হয়নি।":
  "Demo complaint draft only; not submitted to any financial institution.";
}
export function neverSubmitSupportExternally(_case:SupportCase):false{return false;}
