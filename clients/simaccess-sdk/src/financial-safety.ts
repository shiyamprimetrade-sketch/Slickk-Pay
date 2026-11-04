/** Cross-cutting invariant monitor for fictional access, accounting and claims. */
import {failure} from "./errors.js";
import type {SampleQuote} from "./quotes.js";
import type {ReviewedPreview} from "./requests.js";
import type {CashDialogue} from "./cash.js";
import type {PreviewReceipt} from "./receipts.js";
import type {SandboxCapabilities} from "./capabilities.js";
import type {LabRuntime} from "./sdk-runtime.js";
export type SafetyKind="quote"|"request"|"cash"|"receipt"|"capability"|"runtime";
export interface SafetyCheck {
 readonly kind:SafetyKind;readonly passed:boolean;
 readonly rulesChecked:number;readonly errors:readonly string[];
 readonly simulation:true;readonly productionApproved:false;
}
export function checkFinancialSafety(kind:"quote",value:SampleQuote):SafetyCheck;
export function checkFinancialSafety(kind:"request",value:ReviewedPreview):SafetyCheck;
export function checkFinancialSafety(kind:"cash",value:CashDialogue):SafetyCheck;
export function checkFinancialSafety(kind:"receipt",value:PreviewReceipt):SafetyCheck;
export function checkFinancialSafety(kind:"capability",value:SandboxCapabilities):SafetyCheck;
export function checkFinancialSafety(kind:"runtime",value:LabRuntime):SafetyCheck;
export function checkFinancialSafety(kind:SafetyKind,value:unknown):SafetyCheck{
 const fail:string[]=[];
 let rules=0;
 const enforce=(condition:boolean,description:string):void=>{
  rules++;
  if(!condition)fail.push(description);
 };
 if(kind==="quote"){
  const v=value as SampleQuote;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.mayExecute===false,"no posting permission");
  enforce(v.taxesUnverified===true,"unverified tax disclosure");
  enforce(v.total===v.principal+v.fee,"minor-unit conservation");
 }else if(kind==="request"){
  const v=value as ReviewedPreview;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.financialPosting===false,"no journal posting");
  enforce(v.handoverAuthorized===false,"no physical cash authorization");
 }else if(kind==="cash"){
  const v=value as CashDialogue;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.ledgerPosting===false,"no ledger posting");
  enforce(v.handoverAuthorized===false,"no cash handover");
  enforce(v.bothReviewsNotPayment===true,"review does not prove payment");
 }else if(kind==="receipt"){
  const v=value as PreviewReceipt;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.paymentProof===false,"not payment proof");
  enforce(v.bankSettlementProof===false,"not bank proof");
  enforce(v.watermark.length>10,"visible sample watermark");
 }else if(kind==="capability"){
  const v=value as SandboxCapabilities;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.realMoney===false,"no public money");
  enforce(v.canPostMoney===false,"posting disabled");
  enforce(v.canIssueLoans===false,"lending disabled");
  enforce(v.canAuthorizeHandover===false,"handover disabled");
  enforce(v.externalBankConnected===false,"external banks absent");
 }else{
  const v=value as LabRuntime;
  enforce(v.simulation===true,"simulation flag");
  enforce(v.canPostMoney===false,"posting disabled");
  enforce(v.offline.mayQueueFinancialOperation()===false,"no offline transaction queue");
  enforce(v.client.mayExecutePayment()===false,"client cannot execute payment");
 }
 return Object.freeze({kind,passed:fail.length===0,rulesChecked:rules,
  errors:Object.freeze(fail),simulation:true,productionApproved:false});
}
export class FinancialSafetyMonitor {
 private readonly checks:SafetyCheck[]=[];
 check<T extends SafetyKind>(kind:T,value:unknown):SafetyCheck{
  const result=checkFinancialSafety(kind as "quote",value as SampleQuote);
  this.checks.push(result);
  return result;
 }
 report():Readonly<{passed:boolean;checks:number;failed:number;productionApproved:false}>{
  return Object.freeze({passed:this.checks.length>0&&this.checks.every(x=>x.passed),
   checks:this.checks.reduce((n,x)=>n+x.rulesChecked,0),
   failed:this.checks.filter(x=>!x.passed).length,productionApproved:false});
 }
 requireAllSafe():void{
  if(!this.report().passed)throw failure("UNSAFE_CAPABILITY");
 }
 clear():void{this.checks.length=0;}
}
export function neverTurnSafetyCheckIntoLicense(_check:SafetyCheck):false{return false;}
