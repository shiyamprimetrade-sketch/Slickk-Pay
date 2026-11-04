/** Single client-side policy table, always subordinate to backend authorization. */
import {failure,invariant} from "./errors.js";
import type {Role,ActorId} from "./identity.js";
export type Action="health:read"|"profile:read"|"activity:read"|
 "agent_directory:read"|"quote:create_preview"|"quote:review_preview"|
 "quote:cancel_preview"|"request:read"|"cash:review_preview"|
 "support:create_draft"|"support:read_draft"|"qr:issue_preview"|
 "qr:inspect_preview"|"notification:read"|"operator:read"|
 "money:post"|"cash:deliver"|"loan:disburse"|"bank:settle";
const ALLOW:Readonly<Record<Role,readonly Action[]>>=Object.freeze({
 customer:["health:read","profile:read","activity:read","agent_directory:read",
  "quote:create_preview","quote:review_preview","quote:cancel_preview","request:read",
  "cash:review_preview","support:create_draft","support:read_draft",
  "qr:issue_preview","qr:inspect_preview","notification:read"],
 agent:["health:read","profile:read","activity:read","agent_directory:read",
  "quote:create_preview","quote:review_preview","quote:cancel_preview","request:read",
  "cash:review_preview","support:create_draft","support:read_draft",
  "notification:read"],
 merchant:["health:read","profile:read","activity:read","request:read",
  "support:create_draft","support:read_draft","notification:read"],
 operator:["health:read","profile:read","activity:read","agent_directory:read",
  "request:read","operator:read","notification:read"]
});
export interface PolicyDecision{
 readonly allow:boolean;readonly reason:"allowed_preview"|"forbidden"|"server_required";
 readonly clientAuthority:false;readonly simulation:true;
}
export function decideRoleAction(role:Role,action:Action):PolicyDecision{
 const money=["money:post","cash:deliver","loan:disburse","bank:settle"];
 if(money.includes(action))return Object.freeze({allow:false,reason:"server_required",clientAuthority:false,simulation:true});
 const allowed=ALLOW[role].includes(action);
 return Object.freeze({allow:allowed,reason:allowed?"allowed_preview":"forbidden",
  clientAuthority:false,simulation:true});
}
export function requireRoleAction(role:Role,action:Action):void{
 const decision=decideRoleAction(role,action);
 if(!decision.allow)throw failure(decision.reason==="server_required"?
  "SERVER_AUTHORITY_ABSENT":"ROLE_FORBIDDEN");
}
export function resourceScope(owner:ActorId,viewer:ActorId,role:Role):boolean{
 void role;
 return owner===viewer;
}
export function clientPolicyDescription(locale:"en"|"bn"):string{
 return locale==="bn"?"নমুনা অ্যাপের অনুমতি সার্ভারের যাচাইয়ের বিকল্প নয়।":
  "Local role checks only improve UX; the server remains responsible for access decisions.";
}
export function assertNoFinancialPermission():void{
 for(const role of Object.keys(ALLOW) as Role[]){
  for(const action of ["money:post","cash:deliver","loan:disburse","bank:settle"] as Action[]){
   invariant(decideRoleAction(role,action).allow===false,"UNSAFE_CAPABILITY");
  }
 }
}
