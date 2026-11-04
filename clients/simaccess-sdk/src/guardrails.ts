/** Execution-time assertions that forbid capability escalation by any adapter. */
import {failure,invariant} from "./errors.js";
import type {TransportRequest} from "./transport.js";
import type {SandboxCapabilities} from "./capabilities.js";
import type {SessionView} from "./session.js";
export type MoneyMovementVerb="transfer"|"cash_out"|"cash_in"|
 "disburse"|"credit"|"debit"|"settle"|"capture"|"refund";
export interface GuardrailResult {
 readonly accepted:boolean;readonly reason:string;
 readonly mutationAllowsMoney:false;readonly simulation:true;
}
const PROHIBITED_PATH_PARTS=["/ledger/","/wallet/","/balances/post",
 "/settle","/capture","/disburse","/withdraw","/transfer/execute",
 "/cash-handover/confirm","/loans/issue","/deposits/create"];
export function inspectOutgoing(request:TransportRequest):GuardrailResult{
 const route=request.path.toLowerCase();
 const money=PROHIBITED_PATH_PARTS.some(x=>route.includes(x));
 const allowedMethod=request.method==="GET"||request.method==="POST";
 const localNamespace=route.startsWith("/lab/v4/");
 const noExternalRedirect=!route.includes("http:")&&!route.includes("https:");
 const safe=allowedMethod&&!money&&localNamespace&&noExternalRedirect;
 return Object.freeze({accepted:safe,
  reason:safe?"Synthetic access request only":"Financial or external route prohibited",
  mutationAllowsMoney:false,simulation:true});
}
export function requireSafeOutgoing(request:TransportRequest):void{
 if(!inspectOutgoing(request).accepted)throw failure("SERVER_AUTHORITY_ABSENT");
}
export function inspectCapabilityEscalation(previous:SandboxCapabilities,next:SandboxCapabilities):boolean{
 return previous.simulation===true&&next.simulation===true&&
  previous.canPostMoney===false&&next.canPostMoney===false&&
  next.canIssueLoans===false&&next.canAuthorizeHandover===false&&
  next.externalBankConnected===false;
}
export function sessionCannotAuthorizeMoney(view:SessionView):boolean{
 return view.simulation===true && view.balanceAuthority===false;
}
export function rejectFinancialVerb(verb:MoneyMovementVerb):never{
 void verb;
 throw failure("SERVER_AUTHORITY_ABSENT");
}
export function guardrailClaims():readonly string[]{
 return Object.freeze([
  "no production payment gateway requests",
  "no stored-value account mutations",
  "no cash handover authorization",
  "no loan disbursement",
  "no bank deposit or settlement claims",
  "all private sessions remain transient",
  "all customer and agent identities are synthetic",
  "all sample fees are unapproved hypotheses",
  "client-side quote review is not a payment"
 ]);
}
