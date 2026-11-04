/** Cross-language conformance checks for server response shapes and no-money rules. */
import {failure} from "./errors.js";
import {assertNoLiveCapabilities,capabilities} from "./capabilities.js";
import {parseQuote} from "./quotes.js";
import {parseReview} from "./requests.js";
import {parseDialogue,parseChecklist} from "./cash.js";
import {parseDirectory} from "./directory.js";
import {parseReceipt} from "./receipts.js";
import {parseQrInspection} from "./qr.js";
import {parseSupportCase} from "./support.js";
import {parseNotices} from "./notices.js";
import {assertSafePayload} from "./privacy.js";
export type ContractKind="capabilities"|"quote"|"request"|"cash_dialogue"|
 "cash_checklist"|"directory"|"receipt"|"qr_preview"|"support"|"notifications";
export interface ConformanceFinding{
 readonly kind:ContractKind;readonly passed:boolean;readonly messages:readonly string[];
 readonly simulation:true;readonly canMoveMoney:false;
}
export function verifyContract(kind:ContractKind,payload:unknown):ConformanceFinding{
 const errors:string[]=[];
 try{
  assertSafePayload(payload);
  assertNoLiveCapabilities(payload);
  switch(kind){
   case "capabilities":capabilities(payload);break;
   case "quote":parseQuote(payload);break;
   case "request":parseReview(payload);break;
   case "cash_dialogue":parseDialogue(payload);break;
   case "cash_checklist":parseChecklist(payload);break;
   case "directory":parseDirectory(payload);break;
   case "receipt":parseReceipt(payload);break;
   case "qr_preview":parseQrInspection(payload);break;
   case "support":parseSupportCase(payload);break;
   case "notifications":parseNotices(payload);break;
  }
 }catch(error){
  errors.push(error instanceof Error?error.name:"Invalid response");
 }
 return Object.freeze({kind,passed:errors.length===0,messages:Object.freeze(errors),
  simulation:true,canMoveMoney:false});
}
export class ContractSuite {
 private readonly checks:ConformanceFinding[]=[];
 add(kind:ContractKind,payload:unknown):ConformanceFinding{
  const result=verifyContract(kind,payload);
  this.checks.push(result);
  return result;
 }
 failures():readonly ConformanceFinding[]{
  return Object.freeze(this.checks.filter(x=>!x.passed));
 }
 results():readonly ConformanceFinding[]{return Object.freeze([...this.checks]);}
 assertPassed():void{
  if(this.checks.length===0||this.failures().length>0)throw failure("UNTRUSTED_RESPONSE");
 }
 summary():Readonly<{tested:number;passed:number;failed:number;simulation:true}>{
  return Object.freeze({tested:this.checks.length,passed:this.checks.filter(x=>x.passed).length,
   failed:this.failures().length,simulation:true});
 }
 clear():void{this.checks.length=0;}
}
export const REQUIRED_CROSS_LANGUAGE_RULES=Object.freeze([
 "responses must assert simulation=true",
 "quotes must balance principal + fee = total in integer poisha",
 "receipts must be clearly marked not payment proof",
 "cash checklists cannot authorize physical handover",
 "cash dialogue acknowledgments never post ledger entries",
 "local client must not store bank credentials or operator keys",
 "offline data cannot authorize money transfer or disbursement",
 "session tokens cannot be persisted or reused after logout",
 "payment status is never inferred from an HTTP 200 response"
]);
export function codeCoverageChecklist():Readonly<{required:number;financeAuthority:false}>{
 return Object.freeze({required:REQUIRED_CROSS_LANGUAGE_RULES.length,financeAuthority:false});
}
