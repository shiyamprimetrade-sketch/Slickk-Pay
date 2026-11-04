/** Crash/relaunch policy: server lookup required for uncertain preview mutations. */
import {failure,invariant} from "./errors.js";
import {type AttemptEvidence,decideRecovery,type RecoveryDecision} from "./recovery.js";
export type CrashPoint="before_request"|"after_send_unknown"|
 "after_response_before_render"|"after_local_presentation";
export interface CrashScenario{
 readonly point:CrashPoint;readonly operation:"read"|"preview_mutation";
 readonly reference:string;readonly syntheticDataOnly:true;
}
export interface CrashRecoveryPlan{
 readonly mustReauthenticate:boolean;
 readonly mayReplayRead:boolean;readonly mustInspectServer:boolean;
 readonly mayReplayMutation:false;readonly canPostFunds:false;
 readonly instructions:readonly string[];
}
export function planCrashRecovery(scenario:CrashScenario):CrashRecoveryPlan{
 if(!/^[a-z][A-Za-z0-9_:.\-]{7,96}$/.test(scenario.reference))throw failure("INVALID_INPUT");
 const before=scenario.point==="before_request";
 const unknown=scenario.point==="after_send_unknown";
 const mutation=scenario.operation==="preview_mutation";
 const mustInspectServer=mutation&&!before;
 return Object.freeze({mustReauthenticate:true,mayReplayRead:!mutation,
  mustInspectServer,mayReplayMutation:false,canPostFunds:false,
  instructions:Object.freeze([
   "Discard all transient bearer tokens before a new session",
   mustInspectServer?"Inspect the original preview reference on the server":"No uncertain preview mutation to inspect",
   mutation?"Never automatically repeat a preview mutation":"An idempotent read may be refreshed",
   "Never infer settlement from a successful server response"
  ])});
}
export function uncertainMutationRecovery(evidence:AttemptEvidence):RecoveryDecision{
 if(evidence.kind==="money_mutation")return "stop";
 return decideRecovery(evidence).decision;
}
export interface FailureInjectionReview{
 readonly simulation:true;readonly networkPartitionHandled:boolean;
 readonly customerBalanceChanged:false;readonly mustInspectPreviousReference:boolean;
}
export function inspectInjectedFailure(scenario:CrashScenario):FailureInjectionReview{
 const plan=planCrashRecovery(scenario);
 return Object.freeze({simulation:true,networkPartitionHandled:plan.mustReauthenticate,
  customerBalanceChanged:false,mustInspectPreviousReference:plan.mustInspectServer});
}
export function noCrashMayGrantFunds():false{return false;}
