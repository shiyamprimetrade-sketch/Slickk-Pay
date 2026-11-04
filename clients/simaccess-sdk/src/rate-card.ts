/** Transparent pilot tariff research. Server quote overrides every local estimate. */
import {failure,invariant} from "./errors.js";
import {poisha,safeAdd,pilotEstimate,asPpm,type Poisha} from "./money.js";
import type {QuoteOperation} from "./quotes.js";
export interface PilotTariff{
 readonly version:"pilot-2026-unapproved";
 readonly customerFeePpm:number;
 readonly fixedPerThousandPoisha:number;
 readonly merchantFeePpm:number;
 readonly taxRateVerified:false;readonly legallyApproved:false;
 readonly simulation:true;
}
export const ASSUMED_PILOT_TARIFF:PilotTariff=Object.freeze({
 version:"pilot-2026-unapproved",customerFeePpm:0,
 fixedPerThousandPoisha:1099,merchantFeePpm:4500,
 taxRateVerified:false,legallyApproved:false,simulation:true
});
export interface ResearchEstimate {
 readonly operation:QuoteOperation;readonly principal:Poisha;
 readonly estimatedCustomerFee:Poisha;readonly estimatedTotal:Poisha;
 readonly actualServerFee:null;readonly taxesVerified:false;
 readonly mayExecute:false;readonly simulation:true;
}
export function researchEstimate(operation:QuoteOperation,principal:Poisha):ResearchEstimate{
 poisha(principal);
 let fee:Poisha=poisha(0,true);
 if(operation==="cash_out"){
  // ৳10.99 per ৳1,000 as a hypothesis, rounded once at integer minor unit.
  const numerator=BigInt(principal)*1099n;
  const result=(numerator+50_000n)/100_000n;
  if(result>50_000_000n)throw failure("INVALID_MONEY");
  fee=poisha(Number(result),true);
 }
 return Object.freeze({operation,principal,estimatedCustomerFee:fee,
  estimatedTotal:safeAdd(principal,fee),actualServerFee:null,
  taxesVerified:false,mayExecute:false,simulation:true});
}
export function validateAgainstServer(estimate:ResearchEstimate,
 principal:Poisha,actualFee:Poisha):Readonly<{samePrincipal:boolean;matchingPilotFee:boolean;serverIsAuthoritative:true}>{
 poisha(principal);poisha(actualFee,true);
 return Object.freeze({samePrincipal:estimate.principal===principal,
  matchingPilotFee:estimate.estimatedCustomerFee===actualFee,
  serverIsAuthoritative:true});
}
export interface AgentIncentiveHypothesis{
 readonly cashInCommissionPerThousand:150;
 readonly cashOutCommissionPerThousand:550;
 readonly commissionGuaranteed:false;
 readonly actualPartnerContractPresent:false;
}
export const INCENTIVE_HYPOTHESIS:AgentIncentiveHypothesis=Object.freeze({
 cashInCommissionPerThousand:150,cashOutCommissionPerThousand:550,
 commissionGuaranteed:false,actualPartnerContractPresent:false});
export function tariffDisclosure(locale:"en"|"bn"):readonly string[]{
 return Object.freeze(locale==="bn"?
  ["প্রস্তাবিত হার অনুমোদিত নয়","প্রযোজ্য কর যাচাই করা হয়নি","এজেন্টের কমিশন নিশ্চিত নয়"]:
  ["Proposed rates are not approved tariffs","Applicable taxes remain unverified",
   "Agent commissions are hypotheses, not guaranteed earnings"]);
}
export function cannotSetProductionTariff(_tariff:PilotTariff):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
