/** Compare independent sample rows without suggesting actual bank settlement. */
import {failure,invariant} from "./errors.js";
import type {SampleQuote} from "./quotes.js";
import type {ReviewedPreview} from "./requests.js";
import {poisha,feePoisha,safeAdd,type Poisha} from "./money.js";
export type ReconciliationOutcome="matched_preview"|"orphan_quote"|
 "missing_quote"|"quote_mismatch"|"cancelled_preview"|"unreviewed";
export interface ReconciliationLine{
 readonly quoteId:string|null;readonly requestId:string|null;
 readonly outcome:ReconciliationOutcome;
 readonly principal:Poisha;readonly fee:Poisha;readonly total:Poisha;
 readonly simulation:true;readonly bankSettled:false;
}
export interface ReconciliationPreview{
 readonly lines:readonly ReconciliationLine[];
 readonly matched:number;readonly mismatched:number;readonly totalSamplePoisha:Poisha;
 readonly simulation:true;readonly externalBankStatementsChecked:0;
 readonly usableForSettlement:false;
}
export function reconcilePreviews(quotes:readonly SampleQuote[],requests:readonly ReviewedPreview[]):ReconciliationPreview{
 const quoteById=new Map(quotes.map(q=>[q.id,q]));
 const used=new Set<string>();
 const lines:ReconciliationLine[]=[];
 for(const request of requests){
  const quote=quoteById.get(request.quoteId);
  const id=request.quoteId;
  used.add(id);
  if(!quote){
   lines.push(Object.freeze({quoteId:id,requestId:request.id,outcome:"missing_quote",
    principal:poisha(0,true),fee:feePoisha(0),total:poisha(0,true),simulation:true,bankSettled:false}));
   continue;
  }
  const matching=quote.owner===request.owner&&quote.operation===request.operation;
  const outcome:ReconciliationOutcome=!matching?"quote_mismatch":
   request.status==="cancelled"?"cancelled_preview":
   quote.status==="reviewed"&&request.status==="reviewed"?"matched_preview":"unreviewed";
  lines.push(Object.freeze({quoteId:quote.id,requestId:request.id,outcome,
   principal:quote.principal,fee:quote.fee,total:quote.total,simulation:true,bankSettled:false}));
 }
 for(const quote of quotes){
  if(used.has(quote.id))continue;
  lines.push(Object.freeze({quoteId:quote.id,requestId:null,outcome:"orphan_quote",
   principal:quote.principal,fee:quote.fee,total:quote.total,simulation:true,bankSettled:false}));
 }
 let total=0;
 for(const line of lines)if(line.outcome==="matched_preview")total+=line.total;
 if(!Number.isSafeInteger(total)||total>50_000_000)throw failure("INVALID_MONEY");
 return Object.freeze({lines:Object.freeze(lines),matched:lines.filter(x=>x.outcome==="matched_preview").length,
  mismatched:lines.filter(x=>x.outcome!=="matched_preview").length,
  totalSamplePoisha:poisha(total,true),simulation:true,
  externalBankStatementsChecked:0,usableForSettlement:false});
}
export function sampleReconciliationNarrative(result:ReconciliationPreview,locale:"en"|"bn"):string{
 const count=`${result.matched}/${result.lines.length}`;
 return locale==="bn"?`নমুনা রেকর্ড মিলেছে ${count}; বাস্তব ব্যাংক সেটেলমেন্ট যাচাই হয়নি।`:
  `Matched ${count} preview records; no actual bank settlement was checked.`;
}
export function cannotClearSettlementExceptions(_result:ReconciliationPreview):false{return false;}
