/** Agent handover tabletop simulation: no real physical cash or electronic posting. */
import type {ActorId,AgentProfile,MoneyQuote,Locale} from "./types.js";
import {calculatePilotQuote,assertPoisha,formatBDT} from "./money.js";
import {checkSyntheticId} from "./validation.js";
export type HandoverStep="identified"|"quoted"|"awaiting_customer"|"awaiting_agent"|"unresolved"|"cancelled";
export interface HandoverPreview {readonly id:`sim_${string}`;readonly actorId:ActorId;
 readonly agentId:ActorId;readonly step:HandoverStep;readonly operation:"cash_in"|"cash_out";
 readonly amountPoisha:number;readonly quote:MoneyQuote|null;readonly customerAcknowledged:boolean;
 readonly agentAcknowledged:boolean;readonly physicalHandoverVerified:false;
 readonly financialPostingComplete:false;readonly updatedAt:string;readonly note:string;readonly simulation:true;}
export class HandoverError extends Error{constructor(readonly code:string){super(code);this.name="HandoverError";}}
export function newHandoverPreview(actor:ActorId,agent:AgentProfile,operation:"cash_in"|"cash_out",amount:number,now:string):HandoverPreview{
 if(!checkSyntheticId(actor).ok||!agent.simulation||!checkSyntheticId(agent.id).ok)throw new HandoverError("NON_SYNTHETIC_PARTY");
 assertPoisha(amount,false);
 if(operation==="cash_out"&&agent.cashAvailablePoisha<amount)throw new HandoverError("SAMPLE_CASH_SHORTAGE");
 return Object.freeze({id:`sim_handover_${actor.slice(4)}_${agent.id.slice(4)}`,
  actorId:actor,agentId:agent.id,step:"identified",operation,amountPoisha:amount,
  quote:null,customerAcknowledged:false,agentAcknowledged:false,
  physicalHandoverVerified:false,financialPostingComplete:false,updatedAt:now,
  note:"Fictional handover; no real money changed hands.",simulation:true});
}
export function quoteHandover(input:HandoverPreview,at:string):HandoverPreview{
 if(input.step!=="identified")throw new HandoverError("WRONG_STEP");
 const expiresAt=new Date(Date.parse(at)+90_000).toISOString();
 return Object.freeze({...input,step:"quoted",quote:calculatePilotQuote(input.operation,input.amountPoisha,expiresAt),updatedAt:at});
}
export function startHandoverReview(input:HandoverPreview,customerViewed:boolean,at:string):HandoverPreview{
 if(input.step!=="quoted"||!input.quote)throw new HandoverError("QUOTE_REQUIRED");
 if(!customerViewed)throw new HandoverError("CUSTOMER_REVIEW_REQUIRED");
 if(Date.parse(at)>Date.parse(input.quote.expiresAt))throw new HandoverError("QUOTE_EXPIRED");
 return Object.freeze({...input,step:"awaiting_customer",updatedAt:at});
}
export function acknowledgeCustomerDemo(input:HandoverPreview,actor:ActorId,at:string):HandoverPreview{
 if(input.step!=="awaiting_customer")throw new HandoverError("NOT_AWAITING_CUSTOMER");
 if(actor!==input.actorId)throw new HandoverError("CUSTOMER_ID_MISMATCH");
 return Object.freeze({...input,customerAcknowledged:true,step:"awaiting_agent",updatedAt:at});
}
export function acknowledgeAgentDemo(input:HandoverPreview,agent:ActorId,at:string):HandoverPreview{
 if(input.step!=="awaiting_agent"||!input.customerAcknowledged)throw new HandoverError("CUSTOMER_NOT_ACKNOWLEDGED");
 if(agent!==input.agentId)throw new HandoverError("AGENT_ID_MISMATCH");
 // A local acknowledgement MUST NOT convert to a completed cash-out or a posted ledger entry.
 return Object.freeze({...input,agentAcknowledged:true,step:"unresolved",updatedAt:at,
  physicalHandoverVerified:false,financialPostingComplete:false});
}
export function cancelHandoverPreview(input:HandoverPreview,at:string):HandoverPreview{
 if(input.step==="cancelled")return input;
 if(input.step==="unresolved")throw new HandoverError("UNRESOLVED_REVIEW_REQUIRED");
 return Object.freeze({...input,step:"cancelled",updatedAt:at,financialPostingComplete:false,physicalHandoverVerified:false});
}
export function uncertainHandoverWarning(input:HandoverPreview):readonly string[]{
 const warnings=["No real bank or cash settlement has been verified."];
 if(input.step==="unresolved")warnings.push("Both demo participants acknowledged; independent verification is still required.");
 if(input.step==="cancelled")warnings.push("Cancelled sample requests cannot be resumed.");
 warnings.push("Never hand cash to an agent based on an offline screen.");
 return Object.freeze(warnings);
}
export function handoverPresenter(input:HandoverPreview,locale:Locale):{title:string;principal:string;fee:string;step:string;warning:string}{
 const title=input.operation==="cash_out"?(locale==="bn"?"ক্যাশ আউট নমুনা":"Cash-out preview"):
 (locale==="bn"?"ক্যাশ ইন নমুনা":"Cash-in preview");
 return {title,principal:formatBDT(input.amountPoisha,locale),fee:formatBDT(input.quote?.customerFeePoisha??0,locale),
  step:input.step,warning:locale==="bn"?"কোনো আসল নগদ বা ই-ফ্লোট স্থানান্তর হয়নি।":"No real cash or electronic float moved."};
}
export function handoverAuditTrail(item:HandoverPreview):readonly {check:string;passed:boolean}[]{
 return Object.freeze([
  {check:"Synthetic customer",passed:item.actorId.startsWith("sim_")},
  {check:"Synthetic agent",passed:item.agentId.startsWith("sim_")},
  {check:"Quote available",passed:item.quote!==null},
  {check:"Customer demo acknowledgement",passed:item.customerAcknowledged},
  {check:"Agent demo acknowledgement",passed:item.agentAcknowledged},
  {check:"Physical handover verified",passed:false},
  {check:"Server ledger posting complete",passed:false},
 ]);
}
export function canEscalateUncertainHandover(item:HandoverPreview):boolean{return item.step==="unresolved";}
export function handoverCompletionStatus(_item:HandoverPreview):"not_authorized"{return "not_authorized";}
export function reconciliationRequired(item:HandoverPreview):boolean{return item.step==="unresolved"||item.step==="awaiting_agent";}
export function rejectionCodes():readonly string[]{return Object.freeze(["NON_SYNTHETIC_PARTY","NO_REAL_KYC","NO_SERVER_APPROVAL","NO_CASH_HANDOVER_API","NO_LEDGER_POSTING"]);}
