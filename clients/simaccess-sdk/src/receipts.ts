/** Receipt previews must never be mistaken for payment proof. */
import {failure,invariant} from "./errors.js";
import {record,required,text,boolean,mapList} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
export interface ReceiptLine {readonly label:string;readonly value:string;}
export interface PreviewReceipt {
 readonly requestId:ActorId;readonly locale:"en"|"bn";
 readonly watermark:string;readonly lines:readonly ReceiptLine[];
 readonly paymentProof:false;readonly bankSettlementProof:false;
 readonly simulation:true;
}
export function parseReceipt(raw:unknown):PreviewReceipt{
 const o=record(raw);
 invariant(o["simulation"]===true && o["payment_proof"]===false &&
  o["bank_settlement_proof"]===false,"UNSAFE_CAPABILITY");
 const locale=o["locale"]==="bn"?"bn":"en";
 const watermark=text(required(o,"watermark"),10,200);
 if(!(/sample|নমুনা|প্রমাণ নয়/i.test(watermark)))throw failure("UNTRUSTED_RESPONSE");
 const lines=mapList(required(o,"lines"),line=>{
  const item=record(line);
  return Object.freeze({label:text(required(item,"label"),0,100),
   value:text(required(item,"value"),0,240)});
 },30);
 return Object.freeze({requestId:syntheticId(required(o,"request_id")),
  locale,watermark,lines,paymentProof:false,bankSettlementProof:false,simulation:true});
}
export function receiptText(receipt:PreviewReceipt):string{
 const lines=receipt.lines.map(x=>x.label?`${x.label}: ${x.value}`:x.value);
 return [receipt.watermark,...lines,"SIMULATED ONLY — NO CASH OR BANK SETTLEMENT"].join("\n");
}
export function receiptForOwner(receipt:PreviewReceipt,expectedRequest:ActorId):PreviewReceipt{
 if(receipt.requestId!==expectedRequest)throw failure("ROLE_FORBIDDEN");
 return receipt;
}
export function receiptSafeForPrint(receipt:PreviewReceipt):boolean{
 if(receipt.paymentProof||receipt.bankSettlementProof||!receipt.simulation)return false;
 return receipt.lines.length<=30 && receipt.watermark.length>10;
}
export function receiptSummary(receipt:PreviewReceipt):Readonly<{heading:string;explanation:string;canPrint:boolean}>{
 return Object.freeze({heading:receipt.locale==="bn"?"পরীক্ষামূলক রসিদ":"Simulation receipt",
  explanation:receipt.locale==="bn"?"পেমেন্টের প্রমাণ নয়":"Not proof of payment",
  canPrint:receiptSafeForPrint(receipt)});
}
export function createLocalDraftReceipt(requestId:ActorId,locale:"en"|"bn",note:string):PreviewReceipt{
 const safeNote=text(note,0,120);
 if(/(?:card\s*number|otp|pin|password)/i.test(safeNote))throw failure("PRIVACY_VIOLATION");
 return Object.freeze({requestId:syntheticId(requestId),locale,
  watermark:locale==="bn"?"শুধু নমুনা — পেমেন্টের প্রমাণ নয়":"SAMPLE ONLY — NOT PROOF OF PAYMENT",
  lines:Object.freeze([{label:"Draft",value:safeNote}]),
  paymentProof:false,bankSettlementProof:false,simulation:true});
}
export function forbidReceiptAsSettlement(_receipt:PreviewReceipt):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
