/** Form validation never substitutes for server authorization or KYC. */
import type {Validation,ValidationIssue,ActorId,Operation,PaymentDraft,Persona,SupportCase} from "./types.js";
export type FieldInput = Record<string,unknown>;
export function issue(field:string,code:string,description:string):ValidationIssue{return {field,code,description};}
export function ok<T>(value:T):Validation<T>{return {ok:true,value};}
export function invalid<T>(...issues:readonly ValidationIssue[]):Validation<T>{return {ok:false,issues};}
export function mergeIssues(...groups:readonly (readonly ValidationIssue[])[]):readonly ValidationIssue[]{return Object.freeze(groups.flat());}
export function checkString(value:unknown,field:string,min:number,max:number):Validation<string>{
 if(typeof value!=="string")return invalid(issue(field,"type","Expected text"));
 const normalized=value.normalize("NFC").trim();
 if(normalized.length<min)return invalid(issue(field,"short",`At least ${min} characters required`));
 if(normalized.length>max)return invalid(issue(field,"long",`At most ${max} characters allowed`));
 if(/[\u0000-\u001F\u007F-\u009F]/.test(normalized))return invalid(issue(field,"control","Control characters are not permitted"));
 return ok(normalized);
}
export function checkSafeNote(value:unknown):Validation<string>{
 if(value===null||value===undefined||value==="")return ok("");
 const parsed=checkString(value,"note",0,140);
 if(!parsed.ok)return parsed;
 if(/(?:https?:\/\/|<script|\b(?:password|otp|pin)\s*[:=])/i.test(parsed.value))return invalid(issue("note","sensitive","Avoid links, secrets and credentials"));
 return parsed;
}
export function normalizeBdPhone(value:unknown):Validation<string>{
 if(typeof value!=="string")return invalid(issue("phone","type","Phone number is required"));
 const cleaned=value.replace(/[\s\-()]/g,"");
 const match=/^(?:\+?88)?(01[3-9]\d{8})$/.exec(cleaned);
 if(!match?.[1])return invalid(issue("phone","format","Use a Bangladesh mobile number"));
 return ok("+88"+match[1]);
}
export function maskPhone(phone:string):string{
 const normalized=normalizeBdPhone(phone);
 if(!normalized.ok)return "••••••••";
 return normalized.value.slice(0,6)+"•••••"+normalized.value.slice(-3);
}
export function checkSyntheticId(value:unknown,field="id"):Validation<ActorId>{
 if(typeof value!=="string"||!/^sim_[A-Za-z0-9_:.-]{4,88}$/.test(value))return invalid(issue(field,"not_synthetic","Only fictional identifiers are accepted"));
 return ok(value as ActorId);
}
export function checkIsoTime(value:unknown,field="timestamp"):Validation<string>{
 if(typeof value!=="string"||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(value))return invalid(issue(field,"format","Expected UTC timestamp"));
 const time=Date.parse(value);
 if(!Number.isFinite(time)||new Date(time).toISOString().slice(0,19)!==value.slice(0,19))return invalid(issue(field,"invalid","Unrecognized UTC time"));
 return ok(value);
}
export function validateName(value:unknown):Validation<string>{
 const result=checkString(value,"name",2,80);
 if(!result.ok)return result;
 if(!/^[\p{L}\p{M}\s.'\-]+$/u.test(result.value))return invalid(issue("name","characters","Name contains unsupported characters"));
 return result;
}
export function validateLocation(value:unknown):Validation<string>{
 const r=checkString(value,"location",3,100);
 if(!r.ok)return r;
 if(/\b(?:password|otp|pin)\b/i.test(r.value))return invalid(issue("location","sensitive","Remove credential-like text"));
 return r;
}
export function validateMemoText(value:unknown):Validation<string>{
 const r=checkString(value,"description",10,1000);
 if(!r.ok)return r;
 if(/(?:\b\d{16}\b|-----BEGIN|api[_-]?key\s*[=:])/i.test(r.value))return invalid(issue("description","sensitive","Please redact sensitive information"));
 return r;
}
export function validateDraftTarget(operation:Operation,recipient:unknown,agent:unknown,merchant:unknown):Validation<{recipient:ActorId|null;agent:ActorId|null;merchant:ActorId|null}>{
 const fields:[string,unknown][]=[["recipient",recipient],["agent",agent],["merchant",merchant]];
 const results=fields.map(([name,id])=>id===null||id===undefined?ok<ActorId|null>(null):checkSyntheticId(id,name));
 const errors=results.flatMap(r=>r.ok?[]:r.issues);
 if(errors.length)return invalid(...errors);
 const ids=results.map(r=>r.ok?r.value:null);
 const [a,b,c]=ids;
 if(operation==="transfer"&&!a)return invalid(issue("recipient","required","Recipient required"));
 if((operation==="cash_in"||operation==="cash_out")&&!b)return invalid(issue("agent","required","Agent required"));
 if(operation==="merchant_payment"&&!c)return invalid(issue("merchant","required","Merchant required"));
 if(operation==="balance_inquiry"&&(a||b||c))return invalid(issue("operation","unexpected_target","Balance inquiry has no payee"));
 return ok({recipient:a??null,agent:b??null,merchant:c??null});
}
export function validateAmountText(value:unknown):Validation<string>{
 if(typeof value!=="string"||!/^\d{1,8}(?:\.\d{1,2})?$/.test(value.trim()))return invalid(issue("amount","money","Enter an amount with at most two decimals"));
 const parsed=Number(value.trim());
 if(parsed<10||parsed>500000)return invalid(issue("amount","pilot_range","Sandbox pilot supports ৳10 to ৳500,000"));
 return ok(value.trim());
}
export function validateRole(value:unknown):Validation<Persona>{
 if(value==="customer"||value==="agent"||value==="merchant")return ok(value);
 return invalid(issue("role","unknown","Unknown demo persona"));
}
export function validateSupportForm(input:FieldInput):Validation<{subject:string;category:SupportCase["category"];description:string}>{
 const subject=checkString(input["subject"],"subject",4,100),desc=validateMemoText(input["description"]);
 const category=input["category"];
 const issues=[...(subject.ok?[]:subject.issues),...(desc.ok?[]:desc.issues)];
 if(!["payment","security","agent","technical"].includes(String(category)))issues.push(issue("category","invalid","Choose a category"));
 if(issues.length)return invalid(...issues);
 if(!subject.ok||!desc.ok)throw new Error("unreachable validation state");
 return ok({subject:subject.value,description:desc.value,category:category as SupportCase["category"]});
}
export function validateDraftShape(draft:PaymentDraft):readonly ValidationIssue[]{
 const errors:ValidationIssue[]=[];
 if(draft.simulation!==true||draft.serverState!=="not_sent")errors.push(issue("draft","authority","Draft must not imply server authorization"));
 if(draft.approval!=="not_requested"&&draft.approval!=="requires_server")errors.push(issue("approval","invalid","Invalid approval mode"));
 const owner=checkSyntheticId(draft.ownerId,"ownerId");if(!owner.ok)errors.push(...owner.issues);
 const target=validateDraftTarget(draft.operation,draft.payeeId,draft.agentId,draft.merchantId);
 if(!target.ok)errors.push(...target.issues);
 if(!Number.isSafeInteger(draft.principalPoisha)||draft.principalPoisha<=0)errors.push(issue("principal","invalid","Invalid principal"));
 if(draft.state==="quoted"&&!draft.quote)errors.push(issue("quote","missing","Quoted draft must have a fee preview"));
 return Object.freeze(errors);
}
export function checkMonotonicVersion(oldVersion:number,newVersion:number):Validation<number>{
 if(!Number.isSafeInteger(oldVersion)||!Number.isSafeInteger(newVersion)||newVersion<0)return invalid(issue("version","invalid","Invalid version"));
 if(newVersion<=oldVersion)return invalid(issue("version","stale","Newer version required"));
 return ok(newVersion);
}
export function takeIssues<T>(result:Validation<T>):readonly ValidationIssue[]{return result.ok?[]:result.issues;}
export function firstIssue<T>(result:Validation<T>):string|null{return result.ok?null:(result.issues[0]?.description??"Invalid input");}
export function hasSensitiveHints(value:string):boolean{return /(?:bearer\s+\S+|password\s*[:=]|\b(?:otp|pin)\s*[:=]|BEGIN\s+PRIVATE\s+KEY)/i.test(value);}
export function safeDisplayLabel(value:string,maxLength=80):string{
 const result=checkString(value,"label",0,maxLength);
 return result.ok?result.value:"[redacted]";
}
