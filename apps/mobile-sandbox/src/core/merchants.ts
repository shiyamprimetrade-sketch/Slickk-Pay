/** Sample merchant checkout discovery and fee previews. No settlement is represented. */
import type {ActorId,Locale,MerchantProfile,MoneyQuote,SyntheticTransaction,PaymentDraft} from "./types.js";
import {assertPoisha,calculatePilotQuote,formatBDT,percentBasisPoints} from "./money.js";
import {safeDisplayLabel} from "./validation.js";
export interface MerchantListing {readonly id:ActorId;readonly name:string;readonly category:string;readonly acceptingPreview:boolean;readonly simulation:true;}
export interface MerchantStatement {readonly merchantId:ActorId;readonly grossPoisha:number;readonly proposedFeesPoisha:number;readonly netAfterFeesPoisha:number;readonly count:number;readonly exceptions:number;readonly actualBankSettlementVerified:false;readonly simulation:true;}
export interface MerchantInvoice {readonly id:`sim_${string}`;readonly merchantId:ActorId;readonly description:string;readonly quantity:number;readonly unitPricePoisha:number;readonly totalPoisha:number;readonly issuedAt:string;readonly state:"draft";readonly serverSubmitted:false;readonly simulation:true;}
let invoiceCounter=0;
export function merchantDirectory(profiles:readonly MerchantProfile[],query="",activeOnly=true):readonly MerchantListing[]{
 const needle=query.trim().toLocaleLowerCase("en");if(needle.length>90)throw new Error("INVALID_SEARCH");
 return Object.freeze(profiles.filter(x=>x.simulation===true&&(!activeOnly||x.active))
  .filter(x=>`${x.businessName} ${x.category}`.toLocaleLowerCase("en").includes(needle))
  .map(x=>Object.freeze({id:x.id,name:safeDisplayLabel(x.businessName),category:x.category,
   acceptingPreview:x.active,simulation:true as const})));
}
export function findMerchant(profiles:readonly MerchantProfile[],id:string):MerchantProfile|null{
 return profiles.find(x=>x.id===id&&x.simulation)??null;
}
export function merchantPaymentQuote(profile:MerchantProfile,amountPoisha:number,expiresAt:string):MoneyQuote{
 if(!profile.active||!profile.simulation)throw new Error("MERCHANT_NOT_ACTIVE");
 return calculatePilotQuote("merchant_payment",amountPoisha,expiresAt);
}
export function merchantInvoice(id:ActorId,description:string,quantity:number,unitPrice:number,issuedAt:string):MerchantInvoice{
 if(!/^sim_/.test(id)||description.trim().length<3||description.length>100)throw new Error("INVALID_MERCHANT_INVOICE");
 if(!Number.isSafeInteger(quantity)||quantity<1||quantity>1000)throw new Error("INVALID_QUANTITY");
 assertPoisha(unitPrice,false);
 const total=quantity*unitPrice;assertPoisha(total);
 if(total>50_000_000)throw new Error("INVOICE_TOO_LARGE");
 if(!Number.isFinite(Date.parse(issuedAt)))throw new Error("INVALID_INVOICE_DATE");
 invoiceCounter=(invoiceCounter+1)%1_000_000;
 return Object.freeze({id:`sim_invoice_${String(invoiceCounter).padStart(6,"0")}`,merchantId:id,
  description:description.trim(),quantity,unitPricePoisha:unitPrice,totalPoisha:total,
  issuedAt,state:"draft",serverSubmitted:false,simulation:true});
}
export function estimateMerchantStatement(transactions:readonly SyntheticTransaction[],merchantId:ActorId):MerchantStatement{
 const relevant=transactions.filter(x=>x.ownerId===merchantId&&x.operation==="merchant_payment"&&x.simulation);
 const completed=relevant.filter(x=>x.state==="completed");
 const gross=completed.reduce((sum,x)=>sum+assertPoisha(x.amountPoisha),0);
 const proposedFees=completed.reduce((sum,x)=>sum+percentBasisPoints(x.amountPoisha,45),0);
 assertPoisha(gross);assertPoisha(proposedFees);
 return Object.freeze({merchantId,grossPoisha:gross,proposedFeesPoisha:proposedFees,
  netAfterFeesPoisha:gross-proposedFees,count:completed.length,
  exceptions:relevant.filter(x=>x.state!=="completed").length,
  actualBankSettlementVerified:false,simulation:true});
}
export function merchantStatementRows(transactions:readonly SyntheticTransaction[],merchantId:ActorId,locale:Locale):readonly {ref:string;gross:string;fee:string;net:string;status:string}[]{
 return Object.freeze(transactions.filter(x=>x.ownerId===merchantId&&x.operation==="merchant_payment")
  .map(x=>{const fee=percentBasisPoints(x.amountPoisha,45);return {
   ref:x.reference,gross:formatBDT(x.amountPoisha,locale),fee:formatBDT(fee,locale),
   net:formatBDT(x.amountPoisha-fee,locale),status:x.state};}));
}
export function merchantRiskNotices(profile:MerchantProfile,history:readonly SyntheticTransaction[]):readonly string[]{
 const warnings:string[]=[];
 if(!profile.active)warnings.push("SAMPLE_MERCHANT_INACTIVE");
 if(!profile.settlementAccountId.startsWith("sim_"))warnings.push("NON_SYNTHETIC_SETTLEMENT_ID");
 if(history.filter(x=>x.ownerId===profile.id&&x.state==="review").length)warnings.push("SAMPLE_TRANSACTIONS_UNDER_REVIEW");
 warnings.push("BANK_SETTLEMENT_UNVERIFIED");
 return Object.freeze(warnings);
}
export function calculateMerchantQuoteSpread(quote:MoneyQuote,processorCost:number,refundReserve:number):{gross:number;proposedFee:number;cost:number;margin:number}{
 if(quote.operation!=="merchant_payment")throw new Error("NOT_MERCHANT_QUOTE");
 assertPoisha(processorCost);assertPoisha(refundReserve);
 const cost=processorCost+refundReserve;assertPoisha(cost);
 return {gross:quote.principalPoisha,proposedFee:quote.merchantFeePoisha,cost,
  margin:quote.merchantFeePoisha-cost};
}
export function quotePresentableForMerchant(draft:PaymentDraft):boolean{
 return draft.operation==="merchant_payment"&&draft.quote!==null&&draft.simulation===true&&
  draft.serverState==="not_sent"&&draft.merchantId!==null;
}
export function merchantCapabilities():Readonly<Record<string,boolean>>{
 return Object.freeze({viewSampleTransactions:true,estimatePilotFees:true,prepareSampleInvoice:true,
  createRealPaymentIntent:false,acceptLiveCard:false,sendLiveRefund:false,
  settleToBank:false,issueRealQR:false,viewActualBankReconciliation:false});
}
export interface MerchantKpi {readonly label:string;readonly value:number;readonly caveat:string;}
export function merchantDashboardMetrics(statements:readonly MerchantStatement[]):readonly MerchantKpi[]{
 const count=statements.reduce((n,x)=>n+x.count,0);
 const gross=statements.reduce((n,x)=>n+x.grossPoisha,0);
 const fee=statements.reduce((n,x)=>n+x.proposedFeesPoisha,0);
 const issues=statements.reduce((n,x)=>n+x.exceptions,0);
 return Object.freeze([
  {label:"Sample payments",value:count,caveat:"Fixtures only"},
  {label:"Sample gross poisha",value:gross,caveat:"Not bank turnover"},
  {label:"Unapproved merchant fee",value:fee,caveat:"0.45% pilot hypothesis"},
  {label:"Exception samples",value:issues,caveat:"Not real disputes"},
 ]);
}
export function merchantPaymentRestrictions(profile:MerchantProfile):readonly string[]{
 const issues:string[]=["NO_LIVE_MERCHANT_ONBOARDING","NO_EXTERNAL_SETTLEMENT","NO_REAL_REFUNDS"];
 if(!profile.active)issues.unshift("SAMPLE_MERCHANT_DISABLED");
 return Object.freeze(issues);
}
export function refundPreview(principal:number,previousRefund:number,newRefund:number):{permittedLocally:false;remaining:number;valid:boolean;reason:string}{
 [principal,previousRefund,newRefund].forEach(v=>assertPoisha(v));
 const remaining=Math.max(0,principal-previousRefund);
 return {permittedLocally:false,remaining,valid:newRefund<=remaining&&newRefund>0,
  reason:"No real reversal or settlement endpoint is available"};
}
export function invoiceToDescription(invoice:MerchantInvoice,locale:Locale):string{
 const total=formatBDT(invoice.totalPoisha,locale);
 return `${invoice.description} · ${invoice.quantity} × ${formatBDT(invoice.unitPricePoisha,locale)} = ${total} (SAMPLE)`;
}
