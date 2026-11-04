/** Defensive personal-data minimization, redaction, and user-facing consent. */
import {failure,invariant} from "./errors.js";
import {text,record} from "./primitives.js";
export interface PrivacyFinding {
 readonly safe:boolean;
 readonly blockedKeys:readonly string[];
 readonly redacted:string;
 readonly simulation:true;
}
const FORBIDDEN_KEYS=new Set(["pin","password","passwd","card_number","card_no","cvv",
 "otp","access_token","refresh_token","private_key","secret","national_id","nid"]);
const KEY_PATTERN=/(?:pin|password|secret|cvv|otp|private[_-]?key|card[_-]?no|national[_-]?id)/i;
export function sanitizeDescription(input:string):string{
 let out=text(input,0,1000);
 out=out.replace(/\b01[3-9]\d{8}\b/g,"[phone redacted]");
 out=out.replace(/\b\d{13,19}\b/g,"[number redacted]");
 out=out.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,"[email redacted]");
 out=out.replace(/\b(?:OTP|PIN|CVV|PASSWORD)[:= ]+\S+/gi,"[secret redacted]");
 return out;
}
export function inspectPayload(raw:unknown,maxFields=250):PrivacyFinding{
 const keys:string[]=[];
 let visited=0;
 const check=(value:unknown,depth:number):void=>{
  if(depth>10||visited>maxFields)throw failure("UNTRUSTED_RESPONSE");
  if(!value||typeof value!=="object")return;
  for(const [name,child] of Object.entries(value as Record<string,unknown>)){
   visited++;
   if(FORBIDDEN_KEYS.has(name.toLowerCase())||KEY_PATTERN.test(name))keys.push(name);
   if(child&&typeof child==="object")check(child,depth+1);
  }
 };
 check(raw,0);
 return Object.freeze({safe:keys.length===0,blockedKeys:Object.freeze(keys),
  redacted:keys.length>0?"[private fields withheld]":"[safe synthetic record]",simulation:true});
}
export function maskDeviceId(raw:string):string{
 const value=text(raw,8,92);
 return value.slice(0,7)+"••••"+value.slice(-4);
}
export function maskPersonId(raw:string):string{
 const value=text(raw,8,92);
 return value.slice(0,6)+"•••"+value.slice(-2);
}
export function maskedActorSummary(raw:unknown):Readonly<Record<string,string|boolean>>{
 const o=record(raw);
 const actor=String(o["actor_id"]??"sim_unknown");
 if(!actor.startsWith("sim_"))throw failure("PRIVACY_VIOLATION");
 return Object.freeze({actor:maskPersonId(actor),role:String(o["role"]??"unknown"),simulation:true});
}
export interface ConsentDisplay {
 readonly purpose:string;readonly expiresOnExit:true;
 readonly storesSecret:false;readonly permitsRealPayments:false;
 readonly notice:string;
}
export function demoConsent(locale:"en"|"bn"):ConsentDisplay{
 const notice=locale==="bn"?"এই অ্যাপ কাল্পনিক তথ্য ব্যবহার করে। প্রকৃত পরিচয় বা পিন দেবেন না।":
  "This app uses fictional data. Never enter a real PIN, password or government identity.";
 return Object.freeze({purpose:"Synthetic access demonstration",expiresOnExit:true,
  storesSecret:false,permitsRealPayments:false,notice});
}
export function mustNotPersistIdentity(_raw:unknown):false{return false;}
export function assertSafePayload(value:unknown):void{
 const report=inspectPayload(value);
 if(!report.safe)throw failure("PRIVACY_VIOLATION");
}
