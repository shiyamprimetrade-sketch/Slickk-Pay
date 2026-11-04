/** Explainable visibility rules for synthetic personas, not real underwriting. */
import {failure} from "./errors.js";
import type {Role} from "./identity.js";
import type {SampleQuote,QuoteOperation} from "./quotes.js";
export interface EligibilityDecision{
 readonly availableForPreview:boolean;
 readonly financialActivationApproved:false;
 readonly reason:string;readonly requiresServerAuthorization:true;
 readonly simulation:true;
}
export function eligibilityForPreview(role:Role,operation:QuoteOperation):EligibilityDecision{
 const allowed=operation==="cash_in"?role==="agent":role==="customer";
 return Object.freeze({availableForPreview:allowed,financialActivationApproved:false,
  reason:allowed?"Synthetic preview permitted":"Role not eligible for this preview",
  requiresServerAuthorization:true,simulation:true});
}
export function quoteEligibility(role:Role,quote:SampleQuote):EligibilityDecision{
 if(quote.status!=="quoted")return Object.freeze({availableForPreview:false,
  financialActivationApproved:false,reason:"Quote is no longer reviewable",
  requiresServerAuthorization:true,simulation:true});
 return eligibilityForPreview(role,quote.operation);
}
export type Product="customer_transfer"|"agent_cash_in"|"agent_cash_out"|
 "merchant_preview"|"loan_research"|"deposit"|"bank_account";
export function supportedProducts():readonly Product[]{
 return Object.freeze(["customer_transfer","agent_cash_in","agent_cash_out",
  "merchant_preview","loan_research"]);
}
export function productVisibility(role:Role,product:Product):EligibilityDecision{
 const available=(product==="customer_transfer"&&role==="customer")||
  (product==="agent_cash_in"&&role==="agent")||
  (product==="agent_cash_out"&&role==="customer")||
  (product==="merchant_preview"&&role==="customer")||
  (product==="loan_research"&&role==="operator");
 return Object.freeze({availableForPreview:available,
  financialActivationApproved:false,
  reason:available?"Synthetic content only":"This product is not available for the selected demo role",
  requiresServerAuthorization:true,simulation:true});
}
export function neverAdvertiseProductionLoan(_role:Role):false{return false;}
export function denyUnlicensedProduct(_product:Product):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
