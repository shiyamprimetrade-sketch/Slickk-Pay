/** Two-party review checks: acknowledgement is not approval to hand over cash. */
import {failure,invariant} from "./errors.js";
import {record,required,boolean,integer,literal,text} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
export type DialogueState="waiting"|"both_reviewed"|"cancelled";
export interface CashChecklist {
 readonly requestId:ActorId;readonly agent:ActorId;
 readonly sampleCashAvailable:boolean;readonly sampleCustomerPresent:boolean;
 readonly warningsRead:boolean;readonly updatedAt:number;
 readonly simulation:true;readonly handoverAuthorized:false;readonly ledgerPosted:false;
}
export interface CashDialogue {
 readonly requestId:ActorId;readonly customer:ActorId;readonly agent:ActorId;
 readonly customerReviewed:boolean;readonly agentReviewed:boolean;
 readonly state:DialogueState;readonly createdAt:number;readonly updatedAt:number;
 readonly simulation:true;readonly bothReviewsNotPayment:true;
 readonly handoverAuthorized:false;readonly ledgerPosting:false;
}
export function parseChecklist(raw:unknown):CashChecklist{
 const o=record(raw);
 invariant(o["simulation"]===true&&o["handover_authorized"]===false&&o["ledger_posted"]===false,
  "UNSAFE_CAPABILITY");
 return Object.freeze({requestId:syntheticId(required(o,"request_id")),
  agent:syntheticId(required(o,"agent_id")),
  sampleCashAvailable:boolean(required(o,"cash_available")),
  sampleCustomerPresent:boolean(required(o,"customer_present")),
  warningsRead:boolean(required(o,"warnings_acknowledged")),
  updatedAt:integer(required(o,"updated_at"),1),simulation:true,
  handoverAuthorized:false,ledgerPosted:false});
}
export function parseDialogue(raw:unknown):CashDialogue{
 const o=record(raw);
 invariant(o["simulation"]===true&&o["both_reviews_not_payment"]===true&&
  o["cash_handover_authorized"]===false&&o["ledger_posting"]===false,"UNSAFE_CAPABILITY");
 const customer=syntheticId(required(o,"customer_id"));
 const agent=syntheticId(required(o,"agent_id"));
 invariant(customer!==agent);
 const customerReviewed=boolean(required(o,"customer_reviewed"));
 const agentReviewed=boolean(required(o,"agent_reviewed"));
 const state=literal(required(o,"state"),["waiting","both_reviewed","cancelled"] as const);
 if(state==="both_reviewed")invariant(customerReviewed&&agentReviewed);
 return Object.freeze({requestId:syntheticId(required(o,"request_id")),customer,agent,
  customerReviewed,agentReviewed,state,createdAt:integer(required(o,"created_at"),1),
  updatedAt:integer(required(o,"updated_at"),1),simulation:true,bothReviewsNotPayment:true,
  handoverAuthorized:false,ledgerPosting:false});
}
export function assertDialogueProgression(previous:CashDialogue,next:CashDialogue):void{
 invariant(previous.requestId===next.requestId&&previous.customer===next.customer&&previous.agent===next.agent);
 invariant(next.updatedAt>=previous.updatedAt);
 if(previous.state==="cancelled"&&next.state!=="cancelled")throw failure("REQUEST_FINAL");
 if(previous.customerReviewed&&!next.customerReviewed)throw failure("UNTRUSTED_RESPONSE");
 if(previous.agentReviewed&&!next.agentReviewed)throw failure("UNTRUSTED_RESPONSE");
 if(next.state==="both_reviewed"&&!(next.agentReviewed&&next.customerReviewed))throw failure("UNTRUSTED_RESPONSE");
}
export function mayAcknowledgeReview(dialogue:CashDialogue,viewer:ActorId):boolean{
 if(dialogue.state!=="waiting")return false;
 if(viewer===dialogue.customer)return !dialogue.customerReviewed;
 if(viewer===dialogue.agent)return !dialogue.agentReviewed;
 return false;
}
export interface TwoPartySummary {
 readonly label:string;readonly reviewProgress:string;
 readonly cashierMayDeliverCash:false;readonly paymentIsSettled:false;
 readonly authenticCustomerAuthorizationPresent:false;
}
export function twoPartySummary(dialogue:CashDialogue,locale:"en"|"bn"):TwoPartySummary{
 const count=Number(dialogue.customerReviewed)+Number(dialogue.agentReviewed);
 const label=locale==="bn"?"শুধু নমুনা পর্যালোচনা":"Sample review only";
 return Object.freeze({label,reviewProgress:`${count}/2`,
  cashierMayDeliverCash:false,paymentIsSettled:false,authenticCustomerAuthorizationPresent:false});
}
export function validateAcknowledgementReference(raw:string):string{
 const ref=text(raw,8,96);
 if(!/^[a-z][A-Za-z0-9_:.\-]{7,95}$/.test(ref))throw failure("INVALID_INPUT");
 return ref;
}
export interface CashChecklistUpdate{
 readonly cash_available?:boolean;
 readonly customer_present?:boolean;
 readonly warnings_acknowledged?:boolean;
}
export function safeChecklistPatch(update:CashChecklistUpdate):CashChecklistUpdate{
 const values=Object.entries(update);
 if(values.length===0||values.length>3)throw failure("INVALID_INPUT");
 for(const [key,value] of values){
  if(!["cash_available","customer_present","warnings_acknowledged"].includes(key))throw failure("INVALID_INPUT");
  if(typeof value!=="boolean")throw failure("INVALID_INPUT");
 }
 return Object.freeze({...update});
}
export function denyHandover(_dialogue:CashDialogue):never{throw failure("SERVER_AUTHORITY_ABSENT");}
export function denyCashWithdrawal(_checklist:CashChecklist):never{throw failure("SERVER_AUTHORITY_ABSENT");}
