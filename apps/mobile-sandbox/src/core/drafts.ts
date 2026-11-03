/** Quote and review locally; never mutate the ledger or manufacture server acknowledgments. */
import type {ActorId,PaymentDraft,Operation,MoneyQuote,DraftState,ValidationIssue,ActionAvailability} from "./types.js";
import {calculatePilotQuote,parseBDT,verifyQuote,MoneyError} from "./money.js";
import {checkSafeNote,validateDraftTarget,validateDraftShape,checkSyntheticId,issue} from "./validation.js";
export class DraftError extends Error{constructor(readonly code:string){super(code);this.name="DraftError";}}
export interface DraftInput {readonly operation:Operation;readonly amountText:string;readonly ownerId:ActorId;readonly recipientId?:ActorId|null;readonly agentId?:ActorId|null;readonly merchantId?:ActorId|null;readonly note?:string;}
export interface DraftReview {readonly draft:PaymentDraft;readonly warnings:readonly string[];readonly canPost:false;readonly nextStep:"server_authorization_not_implemented";}
export interface DraftAudit {readonly id:string;readonly at:string;readonly event:string;readonly revision:number;readonly details:string;}
const TERMINAL=new Set<DraftState>(["cancelled","expired"]);
let sequence=0;
function timestamp(value:Date|string):string{
 const iso=value instanceof Date?value.toISOString():value;
 if(!Number.isFinite(Date.parse(iso)))throw new DraftError("INVALID_CLOCK");
 return iso;
}
function nextId():`sim_${string}`{sequence=(sequence+1)%100_000_000;return `sim_draft_${String(sequence).padStart(8,"0")}`;}
function approvalState():"not_requested"{return "not_requested";}
export function createDraft(input:DraftInput,now:string,id:string=nextId()):PaymentDraft{
 const owner=checkSyntheticId(input.ownerId,"ownerId"),draftId=checkSyntheticId(id,"draftId");
 if(!owner.ok||!draftId.ok)throw new DraftError("INVALID_SYNTHETIC_ID");
 const target=validateDraftTarget(input.operation,input.recipientId??null,input.agentId??null,input.merchantId??null);
 if(!target.ok)throw new DraftError("INVALID_TARGET");
 const note=checkSafeNote(input.note??"");if(!note.ok)throw new DraftError("INVALID_NOTE");
 let amount:number;
 try{amount=parseBDT(input.amountText);}catch{throw new DraftError("INVALID_AMOUNT");}
 if(amount<=0)throw new DraftError("ZERO_AMOUNT");
 const at=timestamp(now);
 return Object.freeze({simulation:true,dataProvenance:"fixture",id:draftId.value,
  ownerId:owner.value,operation:input.operation,payeeId:target.value.recipient,
  agentId:target.value.agent,merchantId:target.value.merchant,
  principalPoisha:amount,note:note.value,state:"editing",quote:null,
  approval:approvalState(),consent:"not_requested",serverState:"not_sent",
  createdAt:at,updatedAt:at,revision:1});
}
function transition(draft:PaymentDraft,changes:Partial<PaymentDraft>,now:string):PaymentDraft{
 if(TERMINAL.has(draft.state))throw new DraftError("TERMINAL_DRAFT");
 if(draft.simulation!==true||draft.serverState!=="not_sent")throw new DraftError("FOREIGN_DRAFT");
 const next=Object.freeze({...draft,...changes,updatedAt:timestamp(now),revision:draft.revision+1,
  simulation:true as const,dataProvenance:"fixture" as const,serverState:"not_sent" as const});
 const errors=validateDraftShape(next);if(errors.length)throw new DraftError(errors[0]?.code??"INVALID_DRAFT");
 return next;
}
export function quoteDraft(draft:PaymentDraft,now:string,ttlMs=120_000):PaymentDraft{
 if(draft.state!=="editing"&&draft.state!=="quoted")throw new DraftError("QUOTE_NOT_ALLOWED");
 if(!Number.isSafeInteger(ttlMs)||ttlMs<10_000||ttlMs>300_000)throw new DraftError("INVALID_TTL");
 const at=Date.parse(now),expiresAt=new Date(at+ttlMs).toISOString();
 let quote:MoneyQuote;
 try{quote=calculatePilotQuote(draft.operation,draft.principalPoisha,expiresAt);}catch(e){if(e instanceof MoneyError)throw new DraftError(e.code);throw e;}
 return transition(draft,{state:"quoted",quote,approval:"requires_server"},now);
}
export function reviewDraft(draft:PaymentDraft,now:string,understoodSimulation:boolean):DraftReview{
 if(draft.state!=="quoted"||!draft.quote)throw new DraftError("DRAFT_NOT_QUOTED");
 if(!verifyQuote(draft.quote,now))throw new DraftError("QUOTE_EXPIRED");
 if(!understoodSimulation)throw new DraftError("SIMULATION_ACK_REQUIRED");
 const reviewed=transition(draft,{state:"reviewed",consent:"draft_only"},now);
 return Object.freeze({draft:reviewed,canPost:false,nextStep:"server_authorization_not_implemented",
  warnings:Object.freeze(["NO_REAL_TRANSACTION","NOT_BANK_SETTLED","PILOT_PRICES_UNAPPROVED","KYC_NOT_PERFORMED"])});
}
export function cancelDraft(draft:PaymentDraft,now:string):PaymentDraft{
 if(draft.state==="cancelled")return draft;
 if(draft.state==="expired")throw new DraftError("ALREADY_EXPIRED");
 return transition(draft,{state:"cancelled",approval:"not_requested",consent:"not_requested"},now);
}
export function expireDraft(draft:PaymentDraft,now:string):PaymentDraft{
 if(draft.state==="expired")return draft;
 if(draft.state==="cancelled")return draft;
 if(draft.quote&&Date.parse(now)<Date.parse(draft.quote.expiresAt))throw new DraftError("QUOTE_STILL_VALID");
 return transition(draft,{state:"expired",approval:"not_requested"},now);
}
export function editDraftAmount(draft:PaymentDraft,amountText:string,now:string):PaymentDraft{
 if(draft.state==="reviewed")throw new DraftError("REVIEWED_DRAFT_LOCKED");
 let amount:number;try{amount=parseBDT(amountText);}catch{throw new DraftError("INVALID_AMOUNT");}
 if(amount<=0)throw new DraftError("ZERO_AMOUNT");
 return transition(draft,{principalPoisha:amount,state:"editing",quote:null,approval:"not_requested",consent:"not_requested"},now);
}
export function editDraftNote(draft:PaymentDraft,noteText:string,now:string):PaymentDraft{
 if(draft.state==="reviewed")throw new DraftError("REVIEWED_DRAFT_LOCKED");
 const note=checkSafeNote(noteText);if(!note.ok)throw new DraftError("INVALID_NOTE");
 return transition(draft,{note:note.value,state:"editing",quote:null,consent:"not_requested"},now);
}
export function draftProblems(draft:PaymentDraft,now:string):readonly ValidationIssue[]{
 const problems=[...validateDraftShape(draft)];
 if(draft.quote&&!verifyQuote(draft.quote,now))problems.push(issue("quote","expired","Rate preview expired"));
 if(draft.operation==="cash_out"&&draft.agentId===null)problems.push(issue("agent","missing","Choose a sample agent"));
 if(draft.state==="reviewed"&&draft.consent!=="draft_only")problems.push(issue("consent","missing","Simulation acknowledgment missing"));
 return Object.freeze(problems);
}
export function draftAvailability(draft:PaymentDraft,network:"offline"|"limited"|"online"):ActionAvailability{
 if(draft.state==="cancelled"||draft.state==="expired")return {enabled:false,needsServer:false,reason:"DRAFT_TERMINAL"};
 if(network==="offline")return {enabled:false,needsServer:true,reason:"OFFLINE_POSTING_PROHIBITED"};
 return {enabled:false,needsServer:true,reason:"NO_AUTHENTICATED_PAYMENT_API"};
}
export function draftSummary(draft:PaymentDraft):Readonly<Record<string,string|number|boolean>>{
 return Object.freeze({id:draft.id,operation:draft.operation,state:draft.state,
  principalPoisha:draft.principalPoisha,hasQuote:!!draft.quote,
  serverAuthorized:false,simulation:true,revision:draft.revision});
}
export class DraftWorkspace{
 private readonly store=new Map<string,PaymentDraft>();
 private readonly audit:DraftAudit[]=[];
 constructor(private readonly ownerId:ActorId){}
 create(input:DraftInput,now:string):PaymentDraft{
  if(input.ownerId!==this.ownerId)throw new DraftError("OWNER_MISMATCH");
  const draft=createDraft(input,now);
  this.store.set(draft.id,draft);this.record(draft,"created","Local fictional draft",now);return draft;
 }
 get(id:string):PaymentDraft{
  const draft=this.store.get(id);if(!draft||draft.ownerId!==this.ownerId)throw new DraftError("NOT_FOUND");
  return draft;
 }
 update(id:string,operation:"quote"|"cancel"|"expire",now:string):PaymentDraft{
  const draft=this.get(id);
  const result=operation==="quote"?quoteDraft(draft,now):operation==="cancel"?cancelDraft(draft,now):expireDraft(draft,now);
  this.store.set(id,result);this.record(result,operation,"No external request",now);return result;
 }
 review(id:string,now:string,consent:boolean):DraftReview{
  const result=reviewDraft(this.get(id),now,consent);
  this.store.set(id,result.draft);this.record(result.draft,"reviewed","Explicit simulation acknowledgment",now);
  return result;
 }
 reviseAmount(id:string,text:string,now:string):PaymentDraft{
  const draft=editDraftAmount(this.get(id),text,now);
  this.store.set(id,draft);this.record(draft,"edited_amount","No money moved",now);return draft;
 }
 list():readonly PaymentDraft[]{return Object.freeze([...this.store.values()].sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)));}
 eventHistory(id:string):readonly DraftAudit[]{this.get(id);return Object.freeze(this.audit.filter(x=>x.id===id).map(x=>({...x})));}
 discard(id:string):void{const existing=this.get(id);if(existing.state==="reviewed")throw new DraftError("REVIEWED_DRAFT_RETAINED");this.store.delete(id);}
 private record(draft:PaymentDraft,event:string,detail:string,at:string):void{
  this.audit.push(Object.freeze({id:draft.id,event,details:detail,revision:draft.revision,at}));
 }
}
export function compareDraftRevisions(previous:PaymentDraft,next:PaymentDraft):readonly string[]{
 const changes:string[]=[];
 if(previous.id!==next.id||previous.ownerId!==next.ownerId)throw new DraftError("DIFFERENT_DRAFTS");
 if(next.revision<=previous.revision)throw new DraftError("NON_MONOTONIC_REVISION");
 if(previous.principalPoisha!==next.principalPoisha)changes.push("principal");
 if(previous.state!==next.state)changes.push("state");
 if(previous.note!==next.note)changes.push("note");
 if(previous.consent!==next.consent)changes.push("consent");
 if(previous.quote?.expiresAt!==next.quote?.expiresAt)changes.push("quote");
 return Object.freeze(changes);
}
