/** Future customer/agent backend contract. No live endpoint or key is bundled. */
import type {ActorId,AppSnapshot,Persona,UiNetwork,PaymentDraft} from "./types.js";
import {auditPrivateSnapshot} from "./privacy.js";
export type FeatureFlag="customer_read"|"agent_read"|"merchant_read"|"sandbox_draft_preview"|
 "server_transfer"|"server_cash_out"|"server_cash_in"|"real_bank_settlement"|"microcredit_live";
export type CapabilitySet=Readonly<Record<FeatureFlag,boolean>>;
export const SAFE_CAPABILITIES:CapabilitySet=Object.freeze({
 customer_read:true,agent_read:true,merchant_read:true,sandbox_draft_preview:true,
 server_transfer:false,server_cash_out:false,server_cash_in:false,
 real_bank_settlement:false,microcredit_live:false,
});
export interface MobileHandshake {readonly schema:"slickk-mobile-lab-v1";readonly simulation:true;
 readonly serverTime:string;readonly backend:"fixtures"|"isolated_sandbox";readonly capabilities:CapabilitySet;
 readonly financialPostingEnabled:false;readonly operatorKeyRequired:false;}
export interface MobileReadContext {readonly actorId:ActorId;readonly persona:Persona;
 readonly requestId:string;readonly network:UiNetwork;readonly interactive:boolean;readonly allowFinancialWrites:false;}
export interface MobileDataSource {
 handshake(context:MobileReadContext):Promise<MobileHandshake>;
 snapshot(context:MobileReadContext):Promise<AppSnapshot>;
}
export class ProtocolError extends Error{constructor(readonly code:string){super(code);this.name="ProtocolError";}}
export function assertSafeHandshake(result:MobileHandshake):void{
 if(result.schema!=="slickk-mobile-lab-v1"||result.simulation!==true||
  result.financialPostingEnabled!==false||result.operatorKeyRequired!==false)throw new ProtocolError("UNSAFE_HANDSHAKE");
 const mustBeFalse:readonly FeatureFlag[]=["server_transfer","server_cash_in","server_cash_out","real_bank_settlement","microcredit_live"];
 if(mustBeFalse.some(key=>result.capabilities[key]!==false))throw new ProtocolError("UNAUTHORIZED_CAPABILITY");
 if(result.backend!=="fixtures"&&result.backend!=="isolated_sandbox")throw new ProtocolError("UNKNOWN_BACKEND");
 if(!Number.isFinite(Date.parse(result.serverTime)))throw new ProtocolError("BAD_SERVER_TIME");
}
export function validateMobileSnapshot(snapshot:AppSnapshot,context:MobileReadContext):void{
 if(snapshot.actor.id!==context.actorId||snapshot.actor.role!==context.persona)throw new ProtocolError("CROSS_PERSONA_SNAPSHOT");
 if(auditPrivateSnapshot(snapshot).length)throw new ProtocolError("UNVERIFIED_MOBILE_DATA");
 if(snapshot.accounts.some(x=>x.ownerId!==context.actorId))throw new ProtocolError("CROSS_ACCOUNT_DATA");
 if(snapshot.transactions.some(x=>x.ownerId!==context.actorId))throw new ProtocolError("CROSS_TRANSACTION_DATA");
 if(snapshot.supportCases.some(x=>x.ownerId!==context.actorId))throw new ProtocolError("CROSS_SUPPORT_CASE");
}
export function buildReadContext(actorId:ActorId,persona:Persona,network:UiNetwork,requestId:string):MobileReadContext{
 if(!actorId.startsWith("sim_")||!requestId.startsWith("sim_")||requestId.length>100)throw new ProtocolError("INVALID_CONTEXT");
 return Object.freeze({actorId,persona,network,requestId,interactive:true,allowFinancialWrites:false});
}
export class FixtureMobileSource implements MobileDataSource {
 constructor(private readonly fixtures:(persona:Persona)=>AppSnapshot){}
 async handshake(_context:MobileReadContext):Promise<MobileHandshake>{
  return Object.freeze({schema:"slickk-mobile-lab-v1",simulation:true,
   serverTime:"2026-11-03T12:00:00Z",backend:"fixtures",capabilities:SAFE_CAPABILITIES,
   financialPostingEnabled:false,operatorKeyRequired:false});
 }
 async snapshot(context:MobileReadContext):Promise<AppSnapshot>{
  const record=this.fixtures(context.persona);
  validateMobileSnapshot(record,context);
  return record;
 }
}
export interface CapabilityResult {readonly permitted:boolean;readonly source:string;readonly reason:string;readonly requiresVerifiedOperator:false;}
export function capabilityDecision(handshake:MobileHandshake,feature:FeatureFlag):CapabilityResult{
 assertSafeHandshake(handshake);
 if(!handshake.capabilities[feature])return {permitted:false,source:"sandbox_fixture",reason:"CAPABILITY_DISABLED",requiresVerifiedOperator:false};
 if(feature.startsWith("server_")||feature==="real_bank_settlement"||feature==="microcredit_live"){
  return {permitted:false,source:"sandbox_fixture",reason:"SERVER_NOT_AUTHORIZED",requiresVerifiedOperator:false};
 }
 return {permitted:true,source:"sandbox_fixture",reason:"READ_ONLY_PREVIEW",requiresVerifiedOperator:false};
}
export interface ReadonlyTransportPolicy {readonly method:"GET";readonly cookies:"omit";readonly cache:"no-store";readonly redirect:"error";readonly budgetBytes:number;}
export function readTransportPolicy():ReadonlyTransportPolicy{return Object.freeze({method:"GET",cookies:"omit",cache:"no-store",redirect:"error",budgetBytes:256*1024});}
export function rejectMobilePosting(_draft:PaymentDraft):never{throw new ProtocolError("NO_MOBILE_POSTING_CONTRACT");}
export function serverResultNotImplementable():never{throw new ProtocolError("NO_VERIFIED_CUSTOMER_API");}
export function compatibilityGate(serverVersion:string,expected="slickk-mobile-lab-v1"):boolean{
 return serverVersion===expected;
}
export function featureNames(handshake:MobileHandshake):readonly {name:FeatureFlag;available:boolean}[]{
 assertSafeHandshake(handshake);
 return Object.freeze((Object.keys(handshake.capabilities) as FeatureFlag[]).map(name=>({name,available:handshake.capabilities[name]})));
}
export function safeErrorMessage(err:unknown):string{
 if(err instanceof ProtocolError)return err.code;
 return "UNVERIFIED_RESPONSE";
}
export function dataSourceSummary(source:MobileDataSource,context:MobileReadContext):Promise<{simulated:boolean;hasWriteApi:false;backend:string}>{
 return source.handshake(context).then(h=>{assertSafeHandshake(h);return {simulated:true,hasWriteApi:false,backend:h.backend};});
}
