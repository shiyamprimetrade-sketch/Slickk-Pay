/** Explicitly synthetic CSV export for sample activity and review receipts. */
import {failure,invariant} from "./errors.js";
import type {ActivityRow} from "./activity.js";
import type {ReviewedPreview} from "./requests.js";
import {toBdtText} from "./money.js";
export type ExportKind="activity"|"preview_requests";
export interface ExportOptions {
 readonly kind:ExportKind;readonly maxRows:number;
 readonly includeSyntheticIdentifiers:boolean;
 readonly requestedByOwner:true;
}
export interface GeneratedExport {
 readonly filename:string;readonly mime:"text/csv";
 readonly contents:string;readonly rows:number;
 readonly watermark:"FICTIONAL DATA - NOT PAYMENT EVIDENCE";
 readonly containsRealCustomerData:false;
 readonly simulation:true;
}
function escapeCell(text:string):string{
 let clean=text.replace(/\r\n?/g," ").replace(/\n/g," ");
 if(/^[=+@-]/.test(clean))clean="'"+clean;
 if(/[",]/.test(clean))clean='"'+clean.replace(/"/g,'""')+'"';
 return clean;
}
export function csvRows(headers:readonly string[],values:readonly (readonly string[])[]):string{
 if(headers.length<1||headers.length>20)throw failure("INVALID_INPUT");
 if(values.some(row=>row.length!==headers.length))throw failure("INVALID_INPUT");
 return [headers,...values].map(row=>row.map(escapeCell).join(",")).join("\r\n")+"\r\n";
}
export function exportActivity(rows:readonly ActivityRow[],options:ExportOptions):GeneratedExport{
 if(options.kind!=="activity"||!options.requestedByOwner)throw failure("ROLE_FORBIDDEN");
 if(!Number.isSafeInteger(options.maxRows)||options.maxRows<1||options.maxRows>500)throw failure("INVALID_INPUT");
 const selected=rows.slice(0,options.maxRows);
 if(selected.some(x=>x.simulation!==true||x.settled!==false))throw failure("UNSAFE_CAPABILITY");
 const content=csvRows(["sample_id","direction","status","amount_bdt","watermark"],
  selected.map(x=>[options.includeSyntheticIdentifiers?x.id:"[sample id hidden]",
   x.direction,x.status,toBdtText(x.amount),"NOT A SETTLED PAYMENT"]));
 return Object.freeze({filename:"slickk_sample_activity.csv",mime:"text/csv",contents:content,
  rows:selected.length,watermark:"FICTIONAL DATA - NOT PAYMENT EVIDENCE",
  containsRealCustomerData:false,simulation:true});
}
export function exportRequests(rows:readonly ReviewedPreview[],options:ExportOptions):GeneratedExport{
 if(options.kind!=="preview_requests"||!options.requestedByOwner)throw failure("ROLE_FORBIDDEN");
 if(!Number.isSafeInteger(options.maxRows)||options.maxRows<1||options.maxRows>500)throw failure("INVALID_INPUT");
 const selected=rows.slice(0,options.maxRows);
 if(selected.some(x=>x.financialPosting||x.handoverAuthorized))throw failure("UNSAFE_CAPABILITY");
 const content=csvRows(["sample_id","operation","review_state","ledger_posted","watermark"],
  selected.map(x=>[options.includeSyntheticIdentifiers?x.id:"[sample id hidden]",
   x.operation,x.status,"false","PREVIEW ONLY"]));
 return Object.freeze({filename:"slickk_sample_requests.csv",mime:"text/csv",contents:content,
  rows:selected.length,watermark:"FICTIONAL DATA - NOT PAYMENT EVIDENCE",
  containsRealCustomerData:false,simulation:true});
}
export function clientMayExportRealStatements():false{return false;}
