/** Explainable simulated risk hints. Never an autonomous customer decision. */
import {failure,invariant} from "./errors.js";
import {poisha,type Poisha} from "./money.js";
import type {SampleQuote} from "./quotes.js";
import type {CashDialogue} from "./cash.js";
import type {AgentPreview} from "./directory.js";
export type RiskBand="low"|"review"|"blocked";
export type RiskReason="large_sample_amount"|"missing_agent_cash"|"quote_expiring"|
 "two_party_review_incomplete"|"agent_location_unverified"|"offline"|"synthetic_data_only";
export interface RiskResult{
 readonly band:RiskBand;readonly reasons:readonly RiskReason[];
 readonly simulation:true;readonly canApprove:false;
 readonly requiresHumanReview:true;
}
export interface RiskInputs{
 readonly quote:SampleQuote;
 readonly agent?:AgentPreview;
 readonly dialogue?:CashDialogue;
 readonly online:boolean;
 readonly nowSeconds:number;
}
export function triageSampleRisk(input:RiskInputs):RiskResult{
 const reasons:RiskReason[]=["synthetic_data_only"];
 const quote=input.quote;
 if(quote.principal>=poisha(1_000_000))reasons.push("large_sample_amount");
 if(!input.online)reasons.push("offline");
 if(quote.expiresAt-input.nowSeconds<30)reasons.push("quote_expiring");
 if(quote.operation==="cash_out"||quote.operation==="cash_in"){
  if(input.dialogue && !(input.dialogue.customerReviewed&&input.dialogue.agentReviewed))
   reasons.push("two_party_review_incomplete");
  if(input.agent){
   if(!input.agent.hasVerifiedLocation)reasons.push("agent_location_unverified");
   if(input.agent.sampleCash<quote.principal)reasons.push("missing_agent_cash");
  }
 }
 const blocked=reasons.includes("offline")||reasons.includes("missing_agent_cash");
 const review=reasons.length>1;
 return Object.freeze({band:blocked?"blocked":review?"review":"low",
  reasons:Object.freeze(reasons),simulation:true,canApprove:false,requiresHumanReview:true});
}
export function explainRisk(result:RiskResult,locale:"en"|"bn"):readonly string[]{
 const en:Record<RiskReason,string>={
  large_sample_amount:"Large fictional amount; exercise manual review",
  missing_agent_cash:"Sample cash preview is lower than requested amount",
  quote_expiring:"The sample quote is close to expiry",
  two_party_review_incomplete:"Customer and agent have not both reviewed",
  agent_location_unverified:"Agent address is not verified",
  offline:"Offline data cannot authorize any action",
  synthetic_data_only:"No real fraud score, KYC or account verification is available"};
 const bn:Record<RiskReason,string>={
  large_sample_amount:"কাল্পনিক বড় অঙ্ক; ম্যানুয়াল পর্যালোচনা প্রয়োজন",
  missing_agent_cash:"এজেন্টের নমুনা নগদ অপর্যাপ্ত",
  quote_expiring:"নমুনা হিসাবের মেয়াদ শেষ হতে যাচ্ছে",
  two_party_review_incomplete:"দুই পক্ষের পর্যালোচনা সম্পন্ন নয়",
  agent_location_unverified:"এজেন্টের ঠিকানা যাচাই করা হয়নি",
  offline:"অফলাইন তথ্য দিয়ে কোনো কাজ অনুমোদিত নয়",
  synthetic_data_only:"বাস্তব জালিয়াতি স্কোর বা পরিচয় যাচাই নেই"};
 return Object.freeze(result.reasons.map(reason=>(locale==="bn"?bn:en)[reason]));
}
export function neverAutoApproveRisk(_finding:RiskResult):false{return false;}
export function riskNeedsActualLender(_finding:RiskResult):true{return true;}
