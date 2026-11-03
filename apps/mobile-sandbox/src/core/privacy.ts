/** Mobile redaction and presentation minimization. Never persists real customer data. */
import type {AppSnapshot,FieldInfo,Notification,SupportCase,Person,SyntheticTransaction} from "./types.js";
import {maskPhone,hasSensitiveHints} from "./validation.js";
export function maskIdentifier(id:string):string{
 if(id.length<10)return "sim_••••";
 return id.slice(0,7)+"••••"+id.slice(-4);
}
export function maskEmail(input:string):string{
 const at=input.lastIndexOf("@");
 if(at<2||at===input.length-1)return "•••";
 return input.slice(0,1)+"•••"+input.slice(at);
}
export function safeTransactionDescription(input:string):string{
 if(hasSensitiveHints(input))return "[redacted: potential credential]";
 const cleaned=input.replace(/[\u0000-\u001f\u007f]/g,"").trim();
 return cleaned.length>100?cleaned.slice(0,97)+"...":cleaned;
}
export function accountFields(account:{id:string;ownerId:string;kind:string;poisha:number;version:number;frozen:boolean}):readonly FieldInfo[]{
 return Object.freeze([
  {label:"Account",value:maskIdentifier(account.id),sensitive:true},
  {label:"Owner",value:maskIdentifier(account.ownerId),sensitive:true},
  {label:"Account type",value:account.kind,sensitive:false},
  {label:"Version",value:String(account.version),sensitive:false},
  {label:"State",value:account.frozen?"FROZEN":"SIMULATION",sensitive:false},
 ]);
}
export function publicPerson(person:Person):{id:string;name:string;maskedPhone:string;region:string;verification:string}{
 return {id:maskIdentifier(person.id),name:person.name,maskedPhone:maskPhone(person.phone),
   region:person.displayArea,verification:"FICTIONAL / NOT VERIFIED"};
}
export function publicTransaction(tx:SyntheticTransaction):Record<string,string|number|boolean>{
 return {reference:maskIdentifier(tx.reference),counterparty:safeTransactionDescription(tx.otherParty),
   operation:tx.operation,state:tx.state,amountPoisha:tx.amountPoisha,feePoisha:tx.feePoisha,
   occurredAt:tx.occurredAt,simulation:true};
}
export function sanitizedSupportCase(item:SupportCase):{subject:string;status:string;category:string;historyCount:number;reference:string}{
 return {subject:safeTransactionDescription(item.subject),status:item.status,category:item.category,
   historyCount:item.history.length,reference:maskIdentifier(item.id)};
}
export function sanitizedNotice(notice:Notification):{id:string;title:string;message:string;severity:string;category:string}{
 return {id:maskIdentifier(notice.id),title:safeTransactionDescription(notice.title),
   message:safeTransactionDescription(notice.message),severity:notice.severity,category:notice.category};
}
export function auditPrivateSnapshot(snapshot:AppSnapshot):readonly string[]{
 const findings:string[]=[];
 if(snapshot.simulation!==true||snapshot.dataProvenance!=="fixture")findings.push("NOT_FIXTURE");
 if(snapshot.actor.verified!==false)findings.push("VERIFICATION_CLAIM");
 if(snapshot.accounts.some(x=>x.simulation!==true||x.currency!=="BDT"))findings.push("ACCOUNT_PROVENANCE");
 if(snapshot.agents.some(x=>x.simulation!==true))findings.push("AGENT_PROVENANCE");
 if(snapshot.merchants.some(x=>x.simulation!==true))findings.push("MERCHANT_PROVENANCE");
 if(snapshot.transactions.some(x=>x.simulation!==true))findings.push("TRANSACTION_PROVENANCE");
 if(snapshot.supportCases.some(x=>x.simulation!==true))findings.push("SUPPORT_PROVENANCE");
 return Object.freeze(findings);
}
export function redactLogRecord(value:unknown,depth=0):unknown{
 if(depth>6)return "[nested]";
 if(Array.isArray(value))return value.slice(0,50).map(x=>redactLogRecord(x,depth+1));
 if(value&&typeof value==="object"){
   const output:Record<string,unknown>={};
   for(const [key,val] of Object.entries(value as Record<string,unknown>)){
     if(/(?:secret|token|password|pin|credential|key|authorization|cookie|phone|email)/i.test(key))output[key]="[REDACTED]";
     else output[key]=redactLogRecord(val,depth+1);
   }
   return output;
 }
 if(typeof value==="string"){
   if(hasSensitiveHints(value))return "[REDACTED]";
   return value.length>160?value.slice(0,160)+"...":value;
 }
 return value;
}
export function redactExportPayload(records:readonly Record<string,unknown>[]):readonly Record<string,unknown>[]{
 return Object.freeze(records.slice(0,500).map(x=>redactLogRecord(x) as Record<string,unknown>));
}
export function piiRiskScore(record:Record<string,unknown>):{score:number;reasons:readonly string[]}{
 const reasons:string[]=[];
 for(const [key,value] of Object.entries(record)){
  if(/password|pin|secret|token|authorization|cookie/i.test(key))reasons.push("CREDENTIAL_FIELD");
  if(/phone|email|nid|address|birth/i.test(key))reasons.push("PERSONAL_FIELD");
  if(typeof value==="string"&&hasSensitiveHints(value))reasons.push("CREDENTIAL_IN_TEXT");
 }
 return {score:new Set(reasons).size,reasons:Object.freeze([...new Set(reasons)])};
}
export function safeSupportSummary(caseItem:SupportCase):string{
 const safe=sanitizedSupportCase(caseItem);
 return `${safe.reference} · ${safe.category} · ${safe.status} · ${safe.subject}`;
}
export function sampleDataAttestation(snapshot:AppSnapshot):string{
 const findings=auditPrivateSnapshot(snapshot);
 return findings.length?`BLOCKED: ${findings.join(",")}`:`SYNTHETIC FIXTURES ONLY: ${snapshot.actor.role.toUpperCase()}`;
}
