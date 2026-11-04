/** QR references are signed by the local lab; this client never verifies issuer keys. */
import {failure,invariant} from "./errors.js";
import {record,required,text,integer} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
import {parseOperation,type QuoteOperation} from "./quotes.js";
import {poisha,type Poisha} from "./money.js";
export interface SampleQr {
 readonly uri:string;readonly simulation:true;readonly canPay:false;
}
export interface QrDetails {
 readonly issuer:ActorId;readonly recipient:ActorId;
 readonly operation:QuoteOperation;readonly amount:Poisha;
 readonly expiresAt:number;readonly simulation:true;readonly paymentAuthorized:false;
}
export function validateSampleQrUri(input:unknown):string{
 const raw=text(input,30,3000);
 let url:URL;
 try{url=new URL(raw);}catch{throw failure("INVALID_INPUT");}
 if(url.protocol!=="slickkpaylab:" || url.hostname!=="request"||url.search||url.hash||
  url.username||url.password||url.port)throw failure("CROSS_ORIGIN_BLOCKED");
 const envelope=url.pathname.replace(/^\//,"");
 const components=envelope.split(".");
 if(components.length!==3||components.some(x=>!/^[A-Za-z0-9_-]{8,2048}$/.test(x)))
  throw failure("INVALID_INPUT");
 return raw;
}
export function parseQrIssue(value:unknown):SampleQr{
 const item=record(value);
 invariant(item["simulation"]===true && item["can_pay"]===false,"UNSAFE_CAPABILITY");
 return Object.freeze({uri:validateSampleQrUri(required(item,"uri")),simulation:true,canPay:false});
}
export function parseQrInspection(value:unknown):QrDetails{
 const item=record(value);
 invariant(item["simulation"]===true && item["payment_authorized"]===false,"UNSAFE_CAPABILITY");
 const op=parseOperation(required(item,"operation"));
 if(op!=="transfer"&&op!=="merchant_payment")throw failure("INVALID_INPUT");
 const issuer=syntheticId(required(item,"issuer"));
 const recipient=syntheticId(required(item,"recipient"));
 invariant(issuer!==recipient);
 return Object.freeze({issuer,recipient,operation:op,
  amount:poisha(required(item,"amount_poisha")),expiresAt:integer(required(item,"expires_at"),1),
  simulation:true,paymentAuthorized:false});
}
export function qrIsFresh(preview:QrDetails,nowSeconds:number):boolean{
 return nowSeconds<preview.expiresAt;
}
export function qrForActor(preview:QrDetails,actor:ActorId):boolean{
 return preview.issuer===actor||preview.recipient===actor;
}
export function qrNotice(locale:"en"|"bn"):string{
 return locale==="bn"?"এই কোড কেবল পরীক্ষামূলক। কোনো অর্থ পাঠানো হবে না।":
 "This QR is for testing only. Scanning cannot send money.";
}
export class LocalQrPreviewStore {
 private readonly seen=new Set<string>();
 inspect(uri:string):boolean{
  const accepted=validateSampleQrUri(uri);
  return this.seen.has(accepted);
 }
 markSeen(uri:string):void{
  const accepted=validateSampleQrUri(uri);
  this.seen.add(accepted);
 }
 clear():void{this.seen.clear();}
 size():number{return this.seen.size;}
 mayAuthorizeScan():false{return false;}
}
export function cannotPayQr(_preview:QrDetails):never{throw failure("SERVER_AUTHORITY_ABSENT");}
