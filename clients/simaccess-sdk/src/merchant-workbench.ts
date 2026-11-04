/** Merchant receipt and invoice previews, with no external acquiring capability. */
import {failure,invariant} from "./errors.js";
import {poisha,type Poisha,moneyLabel,asPpm,pilotEstimate,safeSubtract} from "./money.js";
import type {SampleQuote} from "./quotes.js";
import type {PreviewReceipt} from "./receipts.js";
export interface MerchantEstimate{
 readonly principal:Poisha;readonly merchantFee:Poisha;
 readonly sampleNet:Poisha;readonly realBankSettlement:null;
 readonly pilotRatePpm:4500;readonly rateApproved:false;
 readonly taxIncluded:false;readonly simulation:true;
}
export function merchantIllustrativeFee(principal:Poisha):MerchantEstimate{
 poisha(principal);
 const merchantFee=pilotEstimate(principal,asPpm(4500));
 return Object.freeze({principal,merchantFee,
  sampleNet:safeSubtract(principal,merchantFee),realBankSettlement:null,
  pilotRatePpm:4500,rateApproved:false,taxIncluded:false,simulation:true});
}
export interface MerchantPreviewCard{
 readonly label:string;readonly amount:string;
 readonly fee:string;readonly assumedNet:string;
 readonly bankCredit:"NOT_VERIFIED";
 readonly cannotAcceptPayment:true;readonly simulation:true;
}
export function merchantPreviewCard(principal:Poisha,locale:"en"|"bn"):MerchantPreviewCard{
 const estimate=merchantIllustrativeFee(principal);
 return Object.freeze({label:locale==="bn"?"ব্যবসায়ীর নমুনা হিসাব":"Merchant fee hypothesis",
  amount:moneyLabel(estimate.principal,locale),
  fee:moneyLabel(estimate.merchantFee,locale),
  assumedNet:moneyLabel(estimate.sampleNet,locale),bankCredit:"NOT_VERIFIED",
  cannotAcceptPayment:true,simulation:true});
}
export function isMerchantPreview(quote:SampleQuote):boolean{
 return quote.operation==="merchant_payment";
}
export function merchantReceiptIsNotSettlement(receipt:PreviewReceipt):boolean{
 return receipt.paymentProof===false&&receipt.bankSettlementProof===false;
}
export function cannotSettleMerchant(_estimate:MerchantEstimate):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
