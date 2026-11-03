/** Preview-only receipts with deterministic non-cryptographic display identifiers. */
import type {ReceiptData,ReceiptLine,Locale,SyntheticTransaction,PaymentDraft,MoneyQuote,Persona} from "./types.js";
import {formatBDT} from "./money.js";
import {maskIdentifier,safeTransactionDescription} from "./privacy.js";
import {localTime,operationLabel,statusLabel,t} from "./locales.js";
import type {TranslationKey} from "./locales.js";
export interface ReceiptOptions {readonly locale:Locale;readonly showFullSyntheticId?:boolean;readonly includeFee?:boolean;}
function digestText(input:string):string{
 // Display-only checksum. It is not a digital signature and must never authenticate a payment.
 let value=2166136261;
 for(const codePoint of input){value^=codePoint.codePointAt(0)??0;value=Math.imul(value,16777619)>>>0;}
 return value.toString(16).padStart(8,"0");
}
function line(title:string,value:string,emphasis=false):ReceiptLine{return Object.freeze({title,value,emphasis});}
function receiptId(id:string):`sim_${string}`{return `sim_receipt_${digestText(id)}`;}
export function receiptFromTransaction(tx:SyntheticTransaction,options:ReceiptOptions):ReceiptData{
 if(tx.simulation!==true||tx.dataProvenance!=="fixture")throw new Error("NON_SAMPLE_RECEIPT");
 const locale=options.locale;
 const lines:ReceiptLine[]=[
  line(t(locale,"ref"),options.showFullSyntheticId?tx.reference:maskIdentifier(tx.reference)),
  line(t(locale,"date"),localTime(locale,tx.occurredAt)),
  line(t(locale,"status"),statusLabel(locale,tx.state)),
  line(t(locale,"principal"),formatBDT(tx.amountPoisha,locale),true),
  line(t(locale,"payee"),safeTransactionDescription(tx.otherParty)),
 ];
 if(options.includeFee!==false)lines.push(line(t(locale,"fee"),formatBDT(tx.feePoisha,locale)));
 return Object.freeze({simulation:true,dataProvenance:"fixture",id:receiptId(tx.id),
  title:`${operationLabel(locale,tx.operation)} — ${t(locale,"requestReceipt")}`,
  issuedAt:tx.occurredAt,lines:Object.freeze(lines),
  disclaimer:t(locale,"receiptWarning"),digest:digestText(`${tx.id}:${tx.amountPoisha}:${tx.state}`)});
}
export function receiptFromDraft(draft:PaymentDraft,locale:Locale):ReceiptData{
 if(!draft.quote||draft.simulation!==true)throw new Error("DRAFT_QUOTE_REQUIRED");
 const quote=draft.quote;
 const lines:ReceiptLine[]=[
  line(t(locale,"ref"),maskIdentifier(draft.id)),
  line(t(locale,"date"),localTime(locale,draft.updatedAt)),
  line(t(locale,"principal"),formatBDT(quote.principalPoisha,locale)),
  line(t(locale,"fee"),formatBDT(quote.customerFeePoisha,locale)),
  line(t(locale,"tax"),t(locale,"unknown")),
  line(t(locale,"total"),formatBDT(quote.customerDebitPoisha,locale),true),
  line(t(locale,"status"),t(locale,"notSent")),
 ];
 return Object.freeze({simulation:true,dataProvenance:"fixture",id:receiptId(draft.id),
  title:`${operationLabel(locale,draft.operation)} — ${t(locale,"previewOnly")}`,
  issuedAt:draft.updatedAt,lines:Object.freeze(lines),disclaimer:t(locale,"receiptWarning"),
  digest:digestText(`${draft.id}:${draft.revision}:${quote.customerDebitPoisha}`)});
}
export function receiptProofWarning(receipt:ReceiptData):readonly string[]{
 const warnings:string[]=[];
 if(!receipt.simulation||receipt.dataProvenance!=="fixture")warnings.push("UNVERIFIED_RECEIPT");
 warnings.push("NOT_PROOF_OF_PAYMENT");
 warnings.push("NOT_BANK_SETTLEMENT_EVIDENCE");
 warnings.push("DISPLAY_DIGEST_NOT_CRYPTOGRAPHIC_SIGNATURE");
 return Object.freeze(warnings);
}
export function serializeReceiptAsText(receipt:ReceiptData):string{
 if(receipt.simulation!==true)throw new Error("UNSAFE_EXPORT");
 const lines=[receipt.title,"=".repeat(Math.min(receipt.title.length,55)),
  ...receipt.lines.map(x=>`${x.title}: ${x.value}`),"",receipt.disclaimer,
  "SIMULATION ONLY",`Display checksum: ${receipt.digest}`];
 return lines.join("\n");
}
export function receiptCanBePrinted(receipt:ReceiptData):{allowed:boolean;requiredBanner:string}{
 if(!receipt.simulation||!receipt.disclaimer)return {allowed:false,requiredBanner:"BLOCKED"};
 return {allowed:true,requiredBanner:"DEMO RECEIPT — NOT PROOF OF PAYMENT"};
}
export function previewReceiptForAgent(quote:MoneyQuote,locale:Locale):readonly ReceiptLine[]{
 if(!quote.simulation)throw new Error("NOT_SIMULATED");
 return Object.freeze([
  line(t(locale,"principal"),formatBDT(quote.principalPoisha,locale)),
  line(t(locale,"fee"),formatBDT(quote.customerFeePoisha,locale)),
  line(t(locale,"commissionEarned"),formatBDT(quote.agentCommissionPoisha,locale)),
  line(t(locale,"total"),formatBDT(quote.customerDebitPoisha,locale),true),
  line(t(locale,"serverRequired"),t(locale,"noAuthority")),
 ]);
}
export interface ReceiptSummary {readonly title:string;readonly timestamp:string;readonly amountLabel:string;readonly statusLabel:string;readonly simulation:true;}
export function summarizeReceipt(tx:SyntheticTransaction,locale:Locale):ReceiptSummary{
 return Object.freeze({title:operationLabel(locale,tx.operation),timestamp:localTime(locale,tx.occurredAt),
  amountLabel:formatBDT(tx.amountPoisha,locale),statusLabel:statusLabel(locale,tx.state),simulation:true});
}
export function compareReceiptAmounts(quote:MoneyQuote,tx:SyntheticTransaction):{match:boolean;reason:string}{
 if(!quote.simulation||!tx.simulation)return {match:false,reason:"NOT_SYNTHETIC"};
 if(tx.amountPoisha!==quote.principalPoisha)return {match:false,reason:"PRINCIPAL_MISMATCH"};
 if(tx.operation!==quote.operation)return {match:false,reason:"OPERATION_MISMATCH"};
 if(tx.feePoisha!==quote.customerFeePoisha)return {match:false,reason:"FEE_MISMATCH"};
 return {match:true,reason:"DISPLAY_VALUES_MATCH_ONLY"};
}
export function receiptAuditFields(receipt:ReceiptData):Readonly<Record<string,string|boolean|number>>{
 return Object.freeze({id:receipt.id,simulation:receipt.simulation,lines:receipt.lines.length,
  issuedAt:receipt.issuedAt,hasDisclaimer:receipt.disclaimer.length>0,digest:receipt.digest});
}
export function renderReceiptPairs(receipt:ReceiptData,hideSensitive=true):readonly {label:string;value:string}[]{
 return Object.freeze(receipt.lines.map(x=>({label:x.title,value:hideSensitive&&/\+880\d{10}/.test(x.value)?"[masked]":x.value})));
}
export function receiptLanguageNotice(locale:Locale,persona:Persona):string{
 const role=persona==="customer"?"customer":persona==="agent"?"agent":"merchant";
 const phrase:TranslationKey=role==="agent"?"agentDashboard":role==="merchant"?"merchantDashboard":"dashboard";
 return `${t(locale,phrase)} · ${t(locale,"previewOnly")}`;
}
