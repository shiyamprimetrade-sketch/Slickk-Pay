/** All records in this module are invented test fixtures; they are not customer information. */
import type {Account,ActorId,AgentProfile,AppSnapshot,Locale,MerchantProfile,Notification,Person,Persona,SupportCase,SyntheticTransaction} from "./types.js";
const T="2026-11-03T12:00:00Z";
const customerId="sim_cust_0001" as ActorId;
const agentId="sim_agent_0001" as ActorId;
const merchantId="sim_merchant_0001" as ActorId;
const common={simulation:true as const,dataProvenance:"fixture" as const};
const persons:Readonly<Record<Persona,Person>>=Object.freeze({
 customer:Object.freeze({...common,id:customerId,role:"customer",name:"Demo Rahim",phone:"+8801700000000",locale:"bn",verified:false,displayArea:"Dhaka (sample)"}),
 agent:Object.freeze({...common,id:agentId,role:"agent",name:"Demo Anika",phone:"+8801811111111",locale:"en",verified:false,displayArea:"Chattogram (sample)"}),
 merchant:Object.freeze({...common,id:merchantId,role:"merchant",name:"Demo Karim",phone:"+8801911111111",locale:"en",verified:false,displayArea:"Dhaka (sample)"}),
});
const accountFixtures:readonly Account[]=Object.freeze([
 {...common,id:"sim_account_cust_01",ownerId:customerId,kind:"customer",poisha:524250,currency:"BDT",version:7,frozen:false},
 {...common,id:"sim_account_agent_float_01",ownerId:agentId,kind:"agent_float",poisha:1250000,currency:"BDT",version:3,frozen:false},
 {...common,id:"sim_account_agent_comm_01",ownerId:agentId,kind:"agent_commission",poisha:31990,currency:"BDT",version:9,frozen:false},
 {...common,id:"sim_account_merchant_01",ownerId:merchantId,kind:"merchant",poisha:374500,currency:"BDT",version:4,frozen:false},
]);
const agentFixtures:readonly AgentProfile[]=Object.freeze([
 {...common,id:agentId,actorId:agentId,businessName:"Anika Demo Store",locationLabel:"Agrabad, Chattogram (sample)",cashAvailablePoisha:750000,floatAccountId:"sim_account_agent_float_01",commissionAccountId:"sim_account_agent_comm_01",serviceHours:"09:00–18:00",acceptingRequests:true,qualityStatus:"sample_good"},
 {...common,id:"sim_agent_0002",actorId:"sim_agent_0002",businessName:"Borno Sample Shop",locationLabel:"Banani, Dhaka (sample)",cashAvailablePoisha:210000,floatAccountId:"sim_float_agent02",commissionAccountId:"sim_comm_agent02",serviceHours:"10:00–19:00",acceptingRequests:true,qualityStatus:"sample_good"},
 {...common,id:"sim_agent_0003",actorId:"sim_agent_0003",businessName:"Nila Demo Point",locationLabel:"Dhanmondi, Dhaka (sample)",cashAvailablePoisha:0,floatAccountId:"sim_float_agent03",commissionAccountId:"sim_comm_agent03",serviceHours:"09:00–17:00",acceptingRequests:false,qualityStatus:"sample_review"},
]);
const merchantFixtures:readonly MerchantProfile[]=Object.freeze([
 {...common,id:merchantId,businessName:"Karim Sample Bazaar",category:"Groceries",settlementAccountId:"sim_account_merchant_01",active:true},
 {...common,id:"sim_merchant_0002",businessName:"Demo Books BD",category:"Books",settlementAccountId:"sim_account_merchant_02",active:true},
 {...common,id:"sim_merchant_0003",businessName:"Inactive Demo Cafe",category:"Food",settlementAccountId:"sim_account_merchant_03",active:false},
]);
const transactionFixtures:readonly SyntheticTransaction[]=Object.freeze([
 {...common,id:"sim_tx_000001",ownerId:customerId,otherParty:"Demo Karim",operation:"merchant_payment",amountPoisha:125000,feePoisha:0,currency:"BDT",state:"completed",occurredAt:"2026-11-02T10:20:00Z",reference:"sim_ref_000001",description:"Sample grocery purchase"},
 {...common,id:"sim_tx_000002",ownerId:customerId,otherParty:"Demo Anika",operation:"cash_in",amountPoisha:200000,feePoisha:0,currency:"BDT",state:"completed",occurredAt:"2026-11-01T11:12:00Z",reference:"sim_ref_000002",description:"Sample cash-in"},
 {...common,id:"sim_tx_000003",ownerId:customerId,otherParty:"Demo Borno",operation:"transfer",amountPoisha:75000,feePoisha:0,currency:"BDT",state:"failed",occurredAt:"2026-10-31T15:11:00Z",reference:"sim_ref_000003",description:"Sample failed transfer"},
 {...common,id:"sim_tx_000004",ownerId:customerId,otherParty:"Demo agent",operation:"cash_out",amountPoisha:100000,feePoisha:1099,currency:"BDT",state:"review",occurredAt:"2026-10-30T09:00:00Z",reference:"sim_ref_000004",description:"Fictional handover review"},
 {...common,id:"sim_tx_000005",ownerId:agentId,otherParty:"Demo Rahim",operation:"cash_in",amountPoisha:200000,feePoisha:0,currency:"BDT",state:"completed",occurredAt:"2026-11-01T11:12:00Z",reference:"sim_ref_000005",description:"Agent sample cash-in"},
 {...common,id:"sim_tx_000006",ownerId:agentId,otherParty:"Demo Karim",operation:"cash_out",amountPoisha:50000,feePoisha:550,currency:"BDT",state:"cancelled",occurredAt:"2026-10-30T07:10:00Z",reference:"sim_ref_000006",description:"Sample cancelled withdrawal"},
 {...common,id:"sim_tx_000007",ownerId:merchantId,otherParty:"Demo Rahim",operation:"merchant_payment",amountPoisha:125000,feePoisha:563,currency:"BDT",state:"completed",occurredAt:"2026-11-02T10:20:00Z",reference:"sim_ref_000007",description:"Sample merchant receipt"},
]);
const noticeFixtures:readonly Notification[]=Object.freeze([
 {...common,id:"sim_notice_0001",actorId:customerId,category:"account",severity:"info",title:"Demo profile ready",message:"This is fictitious account information.",createdAt:T,readAt:null,deepLink:"slickkpaylab://activity"},
 {...common,id:"sim_notice_0002",actorId:customerId,category:"security",severity:"warning",title:"No money can be sent",message:"This is a preview. No live payments are available.",createdAt:"2026-11-02T10:00:00Z",readAt:null,deepLink:"slickkpaylab://limitations"},
 {...common,id:"sim_notice_0003",actorId:agentId,category:"cash",severity:"info",title:"Example daily summary",message:"The sample float does not represent actual cash.",createdAt:T,readAt:null,deepLink:"slickkpaylab://agent_dashboard"},
 {...common,id:"sim_notice_0004",actorId:merchantId,category:"merchant",severity:"info",title:"Demo settlement unavailable",message:"Bank settlement has not been verified.",createdAt:T,readAt:null,deepLink:"slickkpaylab://merchant_dashboard"},
]);
const caseFixtures:readonly SupportCase[]=Object.freeze([
 {...common,id:"sim_case_00001",ownerId:customerId,subject:"Fictional delayed cash handover",category:"agent",description:"A demonstration showing what a disputed physical handover may look like.",status:"investigating",relatedTransactionId:"sim_tx_000004",createdAt:T,updatedAt:T,history:[{at:T,action:"opened",detail:"Synthetic case created"}]},
 {...common,id:"sim_case_00002",ownerId:agentId,subject:"Demo float question",category:"technical",description:"A sample support request for agent cash float forecasting.",status:"open",relatedTransactionId:null,createdAt:T,updatedAt:T,history:[]},
]);
export function fixtureActor(persona:Persona):Person{return Object.freeze({...persons[persona]});}
export function sampleSnapshot(persona:Persona="customer",locale:Locale="bn"):AppSnapshot{
 const actor=Object.freeze({...persons[persona],locale});
 return Object.freeze({...common,actor,
  accounts:Object.freeze(accountFixtures.filter(x=>x.ownerId===actor.id)),
  agents:agentFixtures,
  merchants:merchantFixtures,
  transactions:Object.freeze(transactionFixtures.filter(x=>x.ownerId===actor.id)),
  notices:Object.freeze(noticeFixtures.filter(x=>x.actorId===actor.id)),
  supportCases:Object.freeze(caseFixtures.filter(x=>x.ownerId===actor.id)),
  network:"offline" as const,updatedAt:T});
}
export function allSampleAccounts():readonly Account[]{return Object.freeze(accountFixtures.map(x=>Object.freeze({...x})));}
export function allSampleAgents():readonly AgentProfile[]{return Object.freeze(agentFixtures.map(x=>Object.freeze({...x})));}
export function allSampleMerchants():readonly MerchantProfile[]{return Object.freeze(merchantFixtures.map(x=>Object.freeze({...x})));}
export function allSampleTransactions():readonly SyntheticTransaction[]{return Object.freeze(transactionFixtures.map(x=>Object.freeze({...x})));}
export function syntheticTime():string{return T;}
export function fixtureIntegrity():readonly string[]{
 const errors:string[]=[];
 const ids=[...accountFixtures.map(x=>x.id),...transactionFixtures.map(x=>x.id),...agentFixtures.map(x=>x.id),...merchantFixtures.map(x=>x.id)];
 if(new Set(ids).size!==ids.length)errors.push("DUPLICATE_FIXTURE_ID");
 if([...accountFixtures,...agentFixtures,...merchantFixtures,...transactionFixtures].some(x=>x.simulation!==true))errors.push("UNSAFE_FIXTURE");
 if(accountFixtures.some(x=>x.poisha<0||!Number.isSafeInteger(x.poisha)))errors.push("INVALID_BALANCE");
 if(transactionFixtures.some(x=>x.currency!=="BDT"||x.reference.length>80))errors.push("INVALID_TRANSACTION");
 return Object.freeze(errors);
}
