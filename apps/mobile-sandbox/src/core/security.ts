/** Sandbox session policy; never accept real PINs, credentials or bank-issued tokens. */
import type {Persona,ActionAvailability,UiNetwork,PaymentDraft} from "./types.js";
export interface SessionInfo {readonly persona:Persona;readonly issuedAt:number;readonly expiresAt:number;readonly lastActiveAt:number;readonly locked:boolean;readonly actorId:string;readonly simulation:true;}
export interface DeviceContext {readonly appForeground:boolean;readonly screenProtected:boolean;readonly hasTrustedLocalClock:boolean;readonly network:UiNetwork;readonly securityNoticeAcknowledged:boolean;}
export interface AccessDecision extends ActionAvailability {readonly codes:readonly string[];}
const SESSION_MS=15*60*1000;
const IDLE_MS=5*60*1000;
export function startDemoSession(persona:Persona,actorId:string,now:number):SessionInfo{
 if(!["customer","agent","merchant"].includes(persona)||!/^sim_/.test(actorId)||!Number.isSafeInteger(now)||now<0)throw new Error("INVALID_SANDBOX_SESSION");
 return Object.freeze({persona,actorId,issuedAt:now,lastActiveAt:now,expiresAt:now+SESSION_MS,locked:false,simulation:true});
}
export function updateSession(session:SessionInfo,now:number):SessionInfo{
 if(!Number.isSafeInteger(now)||now<session.lastActiveAt)throw new Error("NONMONOTONIC_TIME");
 const expired=now>=session.expiresAt||now-session.lastActiveAt>=IDLE_MS;
 if(expired||session.locked)return Object.freeze({...session,locked:true});
 return Object.freeze({...session,lastActiveAt:now});
}
export function lockSession(session:SessionInfo):SessionInfo{return Object.freeze({...session,locked:true});}
export function needsLocalUnlock(session:SessionInfo,now:number):boolean{return session.locked||now>=session.expiresAt||now-session.lastActiveAt>=IDLE_MS;}
export function unlockDemoSession(previous:SessionInfo,actorId:string,now:number,explicitConsent:boolean):SessionInfo{
 if(previous.actorId!==actorId||!explicitConsent)throw new Error("LOCAL_CONSENT_REQUIRED");
 return startDemoSession(previous.persona,previous.actorId,now);
}
export function mayViewPrivateFixture(session:SessionInfo,device:DeviceContext,now:number):AccessDecision{
 const reasons:string[]=[];
 if(session.simulation!==true)reasons.push("NOT_SIMULATION");
 if(needsLocalUnlock(session,now))reasons.push("SESSION_LOCKED");
 if(!device.appForeground)reasons.push("BACKGROUND");
 if(!device.screenProtected)reasons.push("SCREEN_UNLOCK_REQUIRED");
 if(!device.hasTrustedLocalClock)reasons.push("CLOCK_UNRELIABLE");
 const enabled=reasons.length===0;
 return Object.freeze({enabled,needsServer:false,reason:enabled?"DEMO_VIEW_ALLOWED":"DEMO_VIEW_BLOCKED",codes:Object.freeze(reasons)});
}
export function authorizeFinancialAction(_session:SessionInfo,_device:DeviceContext,_draft:PaymentDraft):AccessDecision{
 // Intentionally unconditionally denied: real authorization is server-owned, not a mobile UI state.
 return Object.freeze({enabled:false,needsServer:true,reason:"SERVER_AUTHORITATIVE_AUTH_REQUIRED",
  codes:Object.freeze(["NO_FINANCIAL_POSTING_API","SYNTHETIC_MODE_ONLY"])});
}
export function mayPrepareQuote(session:SessionInfo,device:DeviceContext,now:number):AccessDecision{
 const view=mayViewPrivateFixture(session,device,now);
 return view.enabled?Object.freeze({enabled:true,needsServer:false,reason:"LOCAL_QUOTE_ONLY",codes:Object.freeze([])}):view;
}
export function mayUseCameraPreview(device:DeviceContext):AccessDecision{
 const reasons:string[]=[];
 if(!device.appForeground)reasons.push("BACKGROUND");
 if(!device.securityNoticeAcknowledged)reasons.push("CONSENT_REQUIRED");
 if(!device.screenProtected)reasons.push("DEVICE_LOCK_REQUIRED");
 return {enabled:reasons.length===0,reason:reasons.length?"CAMERA_BLOCKED":"QR_PREVIEW_ONLY",needsServer:false,codes:reasons};
}
export function offlineActionPolicy(network:UiNetwork):Record<string,AccessDecision>{
 const preview:AccessDecision=Object.freeze({enabled:true,needsServer:false,reason:"PREVIEW_ONLY",codes:[]});
 const denied:AccessDecision=Object.freeze({enabled:false,needsServer:true,reason:network==="offline"?"OFFLINE_NO_BALANCE_POSTING":"NO_POSTING_ENDPOINT",codes:["SERVER_REQUIRED"]});
 return Object.freeze({viewFixtures:preview,prepareQuote:preview,generateDraftReceipt:preview,
  confirmTransfer:denied,agentCashHandover:denied,approveLoan:denied,refund:denied,merchantCapture:denied});
}
export function safeStoragePolicy(item:string):{persist:boolean;secret:boolean;reason:string}{
 const key=item.toLowerCase();
 if(/(?:operator|bank|password|secret|token|pin|credential|api[_-]?key)/.test(key))return {persist:false,secret:true,reason:"NO_SECRET_STORAGE"};
 if(/(?:balance|available|cash|transaction|fee|session)/.test(key))return {persist:false,secret:false,reason:"NO_AUTHORITATIVE_FINANCIAL_CACHE"};
 if(key==="locale"||key==="contrast"||key==="font_scale")return {persist:true,secret:false,reason:"PREFERENCE_ONLY"};
 return {persist:false,secret:false,reason:"DENY_BY_DEFAULT"};
}
export function securityHeaders():Readonly<Record<string,string>>{
 return Object.freeze({"Accept":"application/json","Cache-Control":"no-store","Pragma":"no-cache"});
}
export function classifyMobileFailure(error:unknown):"offline"|"timeout"|"security"|"unknown"{
 const message=error instanceof Error?error.message:String(error);
 if(/network|offline|internet|fetch/i.test(message))return "offline";
 if(/timeout|abort/i.test(message))return "timeout";
 if(/certificate|tls|unsafe|auth|forbidden/i.test(message))return "security";
 return "unknown";
}
export function securityChecklist(device:DeviceContext,session:SessionInfo,now:number):readonly {name:string;passed:boolean}[]{
 return Object.freeze([
  {name:"synthetic account",passed:session.actorId.startsWith("sim_")&&session.simulation},
  {name:"local session unlocked",passed:!needsLocalUnlock(session,now)},
  {name:"screen protection",passed:device.screenProtected},
  {name:"foreground",passed:device.appForeground},
  {name:"trusted clock",passed:device.hasTrustedLocalClock},
  {name:"no financial authorization",passed:true},
 ]);
}
