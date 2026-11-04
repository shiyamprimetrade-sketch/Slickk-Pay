/** Fictional agent directory; neither GPS nor real cash availability is verified. */
import {failure,invariant} from "./errors.js";
import {record,required,boolean,integer,literal,mapList,text} from "./primitives.js";
import {syntheticId,type ActorId} from "./identity.js";
import {feePoisha,type Poisha,poisha,safeSubtract} from "./money.js";
export type SampleRegion="dhaka_demo"|"chattogram_demo"|"khulna_demo"|"sylhet_demo"|"rajshahi_demo";
export interface AgentPreview {
 readonly id:ActorId;readonly label:string;readonly region:SampleRegion;
 readonly sampleCash:Poisha;readonly sampleFloat:Poisha;
 readonly isRealRegisteredAgent:false;readonly hasVerifiedLocation:false;
 readonly acceptsRealCash:false;readonly simulation:true;
}
export interface AgentResult {
 readonly items:readonly AgentPreview[];readonly hasMore:boolean;
 readonly totalMatching:number;readonly simulation:true;
 readonly realLocationVerified:false;
}
export function region(raw:unknown):SampleRegion {
 return literal(raw,["dhaka_demo","chattogram_demo","khulna_demo","sylhet_demo","rajshahi_demo"] as const);
}
export function parseAgent(raw:unknown):AgentPreview {
 const o=record(raw);
 invariant(o["simulation"]===true && o["accepts_real_cash"]===false &&
  o["verified_business_location"]===false && o["registered_financial_agent"]===false,"UNSAFE_CAPABILITY");
 return Object.freeze({id:syntheticId(required(o,"actor_id")),
  label:text(required(o,"label"),1,80),region:region(required(o,"region")),
  sampleCash:feePoisha(required(o,"sample_cash_poisha")),
  sampleFloat:feePoisha(required(o,"sample_float_poisha")),
  isRealRegisteredAgent:false,hasVerifiedLocation:false,acceptsRealCash:false,simulation:true});
}
export function parseDirectory(raw:unknown):AgentResult {
 const o=record(raw);
 invariant(o["simulation"]===true && o["real_location_verified"]===false,"UNSAFE_CAPABILITY");
 const items=mapList(required(o,"items"),parseAgent,100);
 const count=integer(required(o,"total_matching"),0,1_000_000);
 invariant(count>=items.length);
 return Object.freeze({items,hasMore:boolean(required(o,"has_more")),
  totalMatching:count,simulation:true,realLocationVerified:false});
}
export interface DirectorySearch {
 readonly region?:SampleRegion;
 readonly minimumSampleCashPoisha?:Poisha;
 readonly limit?:number;
}
export function validateDirectorySearch(query:DirectorySearch):DirectorySearch{
 if(query.region)region(query.region);
 if(query.minimumSampleCashPoisha!==undefined)feePoisha(query.minimumSampleCashPoisha);
 if(query.limit!==undefined)integer(query.limit,1,100);
 return Object.freeze({...query});
}
export function availableForPreview(agent:AgentPreview,amount:Poisha):boolean{
 poisha(amount);
 return agent.sampleCash>=amount;
}
export function sampleShortfall(agent:AgentPreview,amount:Poisha):Poisha{
 poisha(amount);
 return amount>agent.sampleCash?safeSubtract(amount,agent.sampleCash):feePoisha(0);
}
export function sortedDemoAgents(items:readonly AgentPreview[],search:string):readonly AgentPreview[]{
 const needle=search.trim().toLocaleLowerCase();
 const matches=items.filter(item=>!needle||item.label.toLocaleLowerCase().includes(needle)||item.region.includes(needle));
 return Object.freeze(matches.sort((a,b)=>a.label.localeCompare(b.label)||a.id.localeCompare(b.id)));
}
export function sampleRegionLabel(value:SampleRegion,locale:"en"|"bn"):string{
 const en:Record<SampleRegion,string>={dhaka_demo:"Dhaka (sample)",chattogram_demo:"Chattogram (sample)",
  khulna_demo:"Khulna (sample)",sylhet_demo:"Sylhet (sample)",rajshahi_demo:"Rajshahi (sample)"};
 const bn:Record<SampleRegion,string>={dhaka_demo:"ঢাকা (নমুনা)",chattogram_demo:"চট্টগ্রাম (নমুনা)",
  khulna_demo:"খুলনা (নমুনা)",sylhet_demo:"সিলেট (নমুনা)",rajshahi_demo:"রাজশাহী (নমুনা)"};
 return (locale==="bn"?bn:en)[value];
}
export function requireDemoAgent(agent:AgentPreview):void{
 if(agent.isRealRegisteredAgent||agent.hasVerifiedLocation||agent.acceptsRealCash)throw failure("UNSAFE_CAPABILITY");
}
export function noRealCashEligibility(_agent:AgentPreview):false{return false;}
