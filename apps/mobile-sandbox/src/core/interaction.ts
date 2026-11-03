/** Typed UI intents: financial intents are local previews and never produce a posting command. */
import type {Persona,ActorId,Operation,PaymentDraft,AppSnapshot,UiNetwork,Locale} from "./types.js";
import {checkSyntheticId,checkSafeNote} from "./validation.js";
import {parseBDT,calculatePilotQuote,verifyQuote} from "./money.js";
export type UiIntent={readonly type:"open_screen";readonly screen:string}|
 {readonly type:"prepare_transfer";readonly recipientId:ActorId;readonly amountText:string;readonly memo:string}|
 {readonly type:"prepare_agent_cash";readonly agentId:ActorId;readonly operation:"cash_in"|"cash_out";readonly amountText:string}|
 {readonly type:"prepare_merchant";readonly merchantId:ActorId;readonly amountText:string}|
 {readonly type:"review_receipt";readonly reference:string}|
 {readonly type:"set_network";readonly network:UiNetwork}|
 {readonly type:"change_language";readonly locale:Locale};
export interface IntentOutcome {readonly accepted:boolean;readonly localOnly:true;readonly requiresServerForFunds:true;readonly code:string;
 readonly preview:Readonly<Record<string,string|number|boolean>>;}
export function parseIntent(raw:unknown):UiIntent|null{
 if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
 const value=raw as Record<string,unknown>;
 if(value["type"]==="open_screen"&&typeof value["screen"]==="string"&&value["screen"].length<40)return {type:"open_screen",screen:value["screen"]};
 if(value["type"]==="set_network"&&(value["network"]==="offline"||value["network"]==="limited"||value["network"]==="online"))return {type:"set_network",network:value["network"]};
 if(value["type"]==="change_language"&&(value["locale"]==="bn"||value["locale"]==="en"))return {type:"change_language",locale:value["locale"]};
 if(value["type"]==="review_receipt"&&typeof value["reference"]==="string"&&value["reference"].startsWith("sim_"))return {type:"review_receipt",reference:value["reference"]};
 if(value["type"]==="prepare_transfer"&&typeof value["amountText"]==="string"&&typeof value["memo"]==="string"&&checkSyntheticId(value["recipientId"]).ok)return {type:"prepare_transfer",recipientId:value["recipientId"] as ActorId,amountText:value["amountText"],memo:value["memo"]};
 if(value["type"]==="prepare_agent_cash"&&(value["operation"]==="cash_in"||value["operation"]==="cash_out")&&typeof value["amountText"]==="string"&&checkSyntheticId(value["agentId"]).ok)return {type:"prepare_agent_cash",agentId:value["agentId"] as ActorId,operation:value["operation"],amountText:value["amountText"]};
 if(value["type"]==="prepare_merchant"&&typeof value["amountText"]==="string"&&checkSyntheticId(value["merchantId"]).ok)return {type:"prepare_merchant",merchantId:value["merchantId"] as ActorId,amountText:value["amountText"]};
 return null;
}
export function evaluateIntent(intent:UiIntent,snapshot:AppSnapshot,at:string):IntentOutcome{
 if(!snapshot.simulation||snapshot.dataProvenance!=="fixture")return reject("UNTRUSTED_CONTEXT");
 if(intent.type==="open_screen")return preview({screen:intent.screen},"LOCAL_NAVIGATION");
 if(intent.type==="set_network")return preview({network:intent.network},"LOCAL_NETWORK_HINT");
 if(intent.type==="change_language")return preview({locale:intent.locale},"LOCAL_PREFERENCE");
 if(intent.type==="review_receipt"){
  const row=snapshot.transactions.find(x=>x.reference===intent.reference);
  return row?preview({reference:row.reference,amountPoisha:row.amountPoisha},"SAMPLE_RECEIPT"):reject("SAMPLE_RECEIPT_NOT_FOUND");
 }
 let operation:Operation,amount:string;
 if(intent.type==="prepare_transfer"){
  if(!checkSafeNote(intent.memo).ok)return reject("INVALID_NOTE");
  operation="transfer";amount=intent.amountText;
 }else if(intent.type==="prepare_agent_cash"){
  if(!snapshot.agents.some(x=>x.id===intent.agentId&&x.acceptingRequests))return reject("UNAVAILABLE_SAMPLE_AGENT");
  operation=intent.operation;amount=intent.amountText;
 }else{
  if(!snapshot.merchants.some(x=>x.id===intent.merchantId&&x.active))return reject("UNAVAILABLE_SAMPLE_MERCHANT");
  operation="merchant_payment";amount=intent.amountText;
 }
 try{
  const principal=parseBDT(amount),expires=new Date(Date.parse(at)+60_000).toISOString();
  const quote=calculatePilotQuote(operation,principal,expires);
  if(!verifyQuote(quote,at))return reject("INVALID_QUOTE");
  return preview({operation,principalPoisha:quote.principalPoisha,customerDebitPoisha:quote.customerDebitPoisha},"LOCAL_QUOTE_ONLY");
 }catch{return reject("INVALID_AMOUNT_OR_QUOTE");}
}
function preview(info:Readonly<Record<string,string|number|boolean>>,code:string):IntentOutcome{
 return Object.freeze({accepted:true,localOnly:true,requiresServerForFunds:true,code,preview:Object.freeze({...info})});
}
function reject(code:string):IntentOutcome{return Object.freeze({accepted:false,localOnly:true,requiresServerForFunds:true,code,preview:Object.freeze({})});}
export function canTurnIntoNetworkCommand(_intent:UiIntent):false{return false;}
export function forbiddenFinancialUiCommands():readonly string[]{return Object.freeze(["post_transfer","confirm_handover","settle_merchant","issue_credit","refund_live","credit_balance"]);}
export function rejectsUnknownIntent(raw:unknown):boolean{return parseIntent(raw)===null;}
export function intentNeedsServerForFunds(_intent:UiIntent):true{return true;}
export function intentAudit(intent:UiIntent):Readonly<Record<string,string|boolean>>{
 return Object.freeze({type:intent.type,simulation:true,sentToServer:false,containsRealAccount:false});
}
export function personaIntentPermissions(persona:Persona):readonly UiIntent["type"][]{
 if(persona==="agent")return Object.freeze(["open_screen","prepare_agent_cash","review_receipt","set_network","change_language"]);
 if(persona==="merchant")return Object.freeze(["open_screen","prepare_merchant","review_receipt","set_network","change_language"]);
 return Object.freeze(["open_screen","prepare_transfer","prepare_agent_cash","prepare_merchant","review_receipt","set_network","change_language"]);
}
export function intentAllowedForPersona(intent:UiIntent,persona:Persona):boolean{return personaIntentPermissions(persona).includes(intent.type);}
