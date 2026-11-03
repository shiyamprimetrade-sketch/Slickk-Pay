/** Internal lab QR payload parsing. QR data NEVER initiates a payment. */
import type {ActorId,Operation,Locale} from "./types.js";
import {checkSyntheticId,normalizeBdPhone} from "./validation.js";
export interface LabQrPayload {readonly scheme:"slickkpaylab";readonly version:1;readonly kind:"agent"|"merchant"|"receipt";readonly id:ActorId;readonly simulation:true;readonly label:string;readonly amountPoisha:number|null;readonly reference:string|null;}
export type ParsedQr={readonly ok:true;readonly value:LabQrPayload}|{readonly ok:false;readonly reason:string};
const SCHEME="slickkpaylab";
const MAX_QR_LENGTH=512;
export function buildDemoQR(input:Omit<LabQrPayload,"scheme"|"version"|"simulation">):string{
 if(!["agent","merchant","receipt"].includes(input.kind))throw new Error("BAD_QR_KIND");
 if(!checkSyntheticId(input.id).ok)throw new Error("NON_SYNTHETIC_QR");
 if(input.label.length<2||input.label.length>64||/[<>\u0000-\u001f]/.test(input.label))throw new Error("BAD_QR_LABEL");
 if(input.amountPoisha!==null&&(!Number.isSafeInteger(input.amountPoisha)||input.amountPoisha<=0||input.amountPoisha>50_000_000))throw new Error("BAD_QR_AMOUNT");
 if(input.reference!==null&&!checkSyntheticId(input.reference).ok)throw new Error("BAD_QR_REFERENCE");
 const data=new URL(`${SCHEME}://${input.kind}`);
 data.searchParams.set("v","1");data.searchParams.set("id",input.id);data.searchParams.set("label",input.label);
 if(input.amountPoisha!==null)data.searchParams.set("amount_poisha",String(input.amountPoisha));
 if(input.reference!==null)data.searchParams.set("ref",input.reference);
 if(data.toString().length>MAX_QR_LENGTH)throw new Error("QR_TOO_LONG");
 return data.toString();
}
export function parseDemoQR(text:string):ParsedQr{
 if(typeof text!=="string"||text.length>MAX_QR_LENGTH||text.length<20)return {ok:false,reason:"INVALID_QR_LENGTH"};
 let url:URL;
 try{url=new URL(text);}catch{return {ok:false,reason:"INVALID_QR_URL"};}
 if(url.protocol!==`${SCHEME}:`||url.username||url.password||url.hash||url.pathname!==""||url.port)return {ok:false,reason:"UNTRUSTED_QR_SCHEME"};
 const kind=url.hostname;
 if(kind!=="agent"&&kind!=="merchant"&&kind!=="receipt")return {ok:false,reason:"UNSUPPORTED_QR_KIND"};
 const keys=new Set<string>();let duplicate=false;
 url.searchParams.forEach((_v,k)=>{if(keys.has(k))duplicate=true;keys.add(k);});
 if(duplicate||[...keys].some(k=>!["v","id","label","amount_poisha","ref"].includes(k)))return {ok:false,reason:"AMBIGUOUS_QR_FIELDS"};
 if(url.searchParams.get("v")!=="1")return {ok:false,reason:"UNSUPPORTED_QR_VERSION"};
 const idResult=checkSyntheticId(url.searchParams.get("id"));
 if(!idResult.ok)return {ok:false,reason:"NON_SYNTHETIC_QR"};
 const label=url.searchParams.get("label")??"";
 if(label.length<2||label.length>64||/[<>\u0000-\u001f]/.test(label))return {ok:false,reason:"INVALID_QR_LABEL"};
 const amountText=url.searchParams.get("amount_poisha");let amount:number|null=null;
 if(amountText!==null){
  if(!/^[1-9]\d{0,8}$/.test(amountText))return {ok:false,reason:"INVALID_QR_AMOUNT"};
  amount=Number(amountText);
  if(!Number.isSafeInteger(amount)||amount>50_000_000)return {ok:false,reason:"INVALID_QR_AMOUNT"};
 }
 const refText=url.searchParams.get("ref");
 const ref=refText===null?null:checkSyntheticId(refText);
 if(ref!==null&&!ref.ok)return {ok:false,reason:"INVALID_QR_REFERENCE"};
 return {ok:true,value:Object.freeze({scheme:SCHEME,version:1,kind,id:idResult.value,
  label,amountPoisha:amount,reference:ref===null?null:ref.value,simulation:true})};
}
export function qrPreviewLabel(payload:LabQrPayload,locale:Locale):string{
 const names:Record<LabQrPayload["kind"],{en:string;bn:string}>={agent:{en:"Sample agent",bn:"নমুনা এজেন্ট"},
 merchant:{en:"Sample merchant",bn:"নমুনা ব্যবসায়ী"},receipt:{en:"Sample receipt",bn:"নমুনা রসিদ"}};
 return `${locale==="bn"?names[payload.kind].bn:names[payload.kind].en}: ${payload.label}`;
}
export function qrActionAvailability(payload:LabQrPayload,operation:Operation):{canInspect:boolean;canPay:false;reason:string}{
 if(!payload.simulation)return {canInspect:false,canPay:false,reason:"NON_SYNTHETIC_QR"};
 const applicable=(payload.kind==="agent"&&(operation==="cash_in"||operation==="cash_out"))||
  (payload.kind==="merchant"&&operation==="merchant_payment")||payload.kind==="receipt";
 return {canInspect:applicable,canPay:false,reason:"QR_IS_NOT_PAYMENT_AUTHORIZATION"};
}
export function qrRequiresNetwork(_payload:LabQrPayload):false{return false;}
export function realPaymentQRAllowed():false{return false;}
export function rejectExternalQrScheme(text:string):boolean{
 try{return new URL(text).protocol!=="slickkpaylab:";}catch{return true;}
}
export function badgeForQr(payload:LabQrPayload):string{return `LAB · ${payload.kind.toUpperCase()} · NOT PAYABLE`;}
export function qrPrivacySummary(payload:LabQrPayload):string{
 return `${payload.kind} identifier ${payload.id.slice(0,8)}…; contains no real credential or authentication token`;
}
export function checkQrCardReadable(text:string):{valid:boolean;warning:string}{
 const result=parseDemoQR(text);
 return result.ok?{valid:true,warning:"Local demo data only — no banking QR interoperability"}:
 {valid:false,warning:`Rejected: ${result.reason}`};
}
export function unsafeQrExamples():readonly string[]{return Object.freeze(["https://real-bank.example/pay","bkash://pay?id=123","javascript:alert(1)"]);}
export function validateSampleContactForQr(phone:string):boolean{return normalizeBdPhone(phone).ok;}
