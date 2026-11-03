/** All BDT calculations are integers in poisha; display numbers are never ledger authority. */
import type {MoneyQuote, Operation, Locale} from "./types.js";
export class MoneyError extends Error { constructor(readonly code: string) { super(code); this.name="MoneyError"; } }
const MAX = 9_000_000_000_000;
export function assertPoisha(value: unknown, allowZero=true): number {
  if (typeof value!=="number" || !Number.isSafeInteger(value) || value<0 || value>MAX || (!allowZero&&value===0)) {
    throw new MoneyError("INVALID_MINOR_UNITS");
  }
  return value;
}
export function addPoisha(...amounts: readonly number[]): number {
  let sum=0;
  for (const amount of amounts){sum+=assertPoisha(amount);if(!Number.isSafeInteger(sum)||sum>MAX)throw new MoneyError("OVERFLOW");}
  return sum;
}
export function subtractPoisha(balance: number, debit: number): number {
  assertPoisha(balance);assertPoisha(debit);
  if(debit>balance)throw new MoneyError("INSUFFICIENT_BALANCE");
  return balance-debit;
}
export function multiplyRatio(value:number,numerator:number,denominator:number,mode:"ceil"|"floor"|"half_up"="half_up"):number {
  assertPoisha(value);
  if(!Number.isSafeInteger(numerator)||!Number.isSafeInteger(denominator)||numerator<0||denominator<=0)throw new MoneyError("INVALID_RATE");
  // BigInt avoids overflow from intermediate multiplication and implements deterministic rounding.
  const product=BigInt(value)*BigInt(numerator), divisor=BigInt(denominator);
  const rounded=mode==="ceil"?(product+divisor-1n)/divisor:mode==="floor"?product/divisor:(product+divisor/2n)/divisor;
  const result=Number(rounded);
  return assertPoisha(result);
}
export function parseBDT(text:string):number {
  if(typeof text!=="string"|| !/^(?:0|[1-9]\d{0,10})(?:\.\d{1,2})?$/.test(text.trim()))throw new MoneyError("INVALID_AMOUNT");
  const [whole="0",fraction=""]=text.trim().split(".");
  return assertPoisha(Number(whole)*100+Number(fraction.padEnd(2,"0")));
}
export function formatBDT(poisha:number,locale:Locale="en",includeCurrency=true):string {
  assertPoisha(poisha);
  const whole=Math.floor(poisha/100),fraction=(poisha%100).toString().padStart(2,"0");
  const formatted=new Intl.NumberFormat(locale==="bn"?"bn-BD":"en-BD",{maximumFractionDigits:0}).format(whole);
  const digits=locale==="bn"?fraction.replace(/[0-9]/g,ch=>"০১২৩৪৫৬৭৮৯"[Number(ch)]??ch):fraction;
  return (includeCurrency?"৳":"")+formatted+"."+digits;
}
export function percentBasisPoints(value:number,basisPoints:number):number {
  return multiplyRatio(value,basisPoints,10000,"half_up");
}
export const PILOT_PRICING=Object.freeze({
  version:"PILOT-UNAPPROVED-2026-11",cashOutPer1000:1099,
  cashInAgentCommissionPer1000:150,cashOutAgentCommissionPer1000:550,
  merchantBasisPoints:45,transferFee:0,merchantCustomerFee:0,
});
export function calculatePilotQuote(operation:Operation,principal:number,expiresAt:string):MoneyQuote {
  assertPoisha(principal,false);
  if(principal<1000)throw new MoneyError("BELOW_PILOT_MINIMUM");
  if(principal>50_000_000)throw new MoneyError("ABOVE_PILOT_MAXIMUM");
  let fee=0,commission=0,merchantFee=0;
  if(operation==="cash_out"){
    fee=multiplyRatio(principal,PILOT_PRICING.cashOutPer1000,100_000,"half_up");
    commission=multiplyRatio(principal,PILOT_PRICING.cashOutAgentCommissionPer1000,100_000,"half_up");
  }else if(operation==="cash_in"){
    commission=multiplyRatio(principal,PILOT_PRICING.cashInAgentCommissionPer1000,100_000,"half_up");
  }else if(operation==="merchant_payment"){
    merchantFee=percentBasisPoints(principal,PILOT_PRICING.merchantBasisPoints);
  }
  // Taxes must be provided by an authoritative tariff service; never invent or hide them.
  const tax=0;
  if(commission>fee && operation==="cash_out")throw new MoneyError("NEGATIVE_SPREAD");
  return Object.freeze({simulation:true,dataProvenance:"fixture" as const,operation,
    principalPoisha:principal,customerFeePoisha:fee,taxPoisha:tax,
    customerDebitPoisha:addPoisha(principal,fee,tax),
    recipientCreditPoisha:operation==="merchant_payment"?principal-merchantFee:principal,
    agentCommissionPoisha:commission,merchantFeePoisha:merchantFee,
    basis:"unapproved_pilot_hypothesis" as const,currency:"BDT" as const,
    rateVersion:PILOT_PRICING.version,expiresAt});
}
export function feeBreakdown(quote:MoneyQuote):ReadonlyArray<{label:string;amount:number}>{
  return Object.freeze([
    {label:"principal",amount:assertPoisha(quote.principalPoisha)},
    {label:"customer_fee",amount:assertPoisha(quote.customerFeePoisha)},
    {label:"tax_unverified",amount:assertPoisha(quote.taxPoisha)},
    {label:"total_customer_debit",amount:assertPoisha(quote.customerDebitPoisha)},
  ]);
}
export function verifyQuote(quote:MoneyQuote,now:string):boolean{
  if(quote.simulation!==true || quote.currency!=="BDT" || quote.basis!=="unapproved_pilot_hypothesis")return false;
  if(!Number.isFinite(Date.parse(now))||!Number.isFinite(Date.parse(quote.expiresAt)))return false;
  if(Date.parse(now)>Date.parse(quote.expiresAt))return false;
  try{
    return quote.customerDebitPoisha===addPoisha(quote.principalPoisha,quote.customerFeePoisha,quote.taxPoisha)
       && quote.recipientCreditPoisha+quote.merchantFeePoisha===quote.principalPoisha;
  }catch{return false;}
}
export function quoteMargin(quote:MoneyQuote,providerCost:number,infraCost:number,lossReserve:number):number {
  [providerCost,infraCost,lossReserve].forEach(x=>assertPoisha(x));
  return quote.customerFeePoisha+quote.merchantFeePoisha-quote.agentCommissionPoisha-providerCost-infraCost-lossReserve;
}
export function splitPoisha(amount:number,count:number):ReadonlyArray<number>{
  assertPoisha(amount);if(!Number.isSafeInteger(count)||count<1||count>1000)throw new MoneyError("INVALID_SPLIT");
  const base=Math.floor(amount/count),extra=amount%count;
  return Object.freeze(Array.from({length:count},(_,i)=>base+(i<extra?1:0)));
}
export function sumQuoteDebits(quotes:readonly MoneyQuote[]):number{return addPoisha(...quotes.map(q=>q.customerDebitPoisha));}
