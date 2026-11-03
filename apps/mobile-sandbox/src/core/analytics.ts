/** Observable sample KPIs with explicit provenance and no real bank or customer claims. */
import type {Account,AgentProfile,AppSnapshot,SyntheticTransaction,Persona,Locale} from "./types.js";
import {assertPoisha,formatBDT} from "./money.js";
import {aggregateActivity,operationDistribution} from "./activity.js";
import {agentCommissionEstimate} from "./agents.js";
export interface DemoKpi {readonly key:string;readonly label:string;readonly value:number;readonly unit:"count"|"poisha"|"basis_points";readonly caveat:string;readonly simulation:true;}
export interface DemoDashboard {readonly persona:Persona;readonly kpis:readonly DemoKpi[];readonly transactionsByOperation:Readonly<Record<string,number>>;readonly updatedAt:string;readonly simulation:true;readonly externalSettlementVerified:false;}
function kpi(key:string,label:string,value:number,unit:DemoKpi["unit"],caveat:string):DemoKpi{
 return Object.freeze({key,label,value,unit,caveat,simulation:true});
}
export function customerDashboard(snapshot:AppSnapshot):DemoDashboard{
 const activity=aggregateActivity(snapshot.transactions);
 const balance=snapshot.accounts.filter(x=>x.kind==="customer").reduce((a,x)=>a+assertPoisha(x.poisha),0);
 return Object.freeze({persona:"customer",updatedAt:snapshot.updatedAt,simulation:true,externalSettlementVerified:false,
  transactionsByOperation:operationDistribution(snapshot.transactions),
  kpis:Object.freeze([
   kpi("balance","Fictional balance",balance,"poisha","Not a real deposit"),
   kpi("operations","Sample activities",activity.count,"count","Fixtures only"),
   kpi("completed","Completed examples",activity.successful,"count","Not actual payments"),
   kpi("pending","Review examples",activity.review,"count","Simulated exceptions"),
  ])});
}
export function agentDashboard(snapshot:AppSnapshot):DemoDashboard{
 const float=snapshot.accounts.filter(x=>x.kind==="agent_float").reduce((s,x)=>s+x.poisha,0);
 const commissions=snapshot.accounts.filter(x=>x.kind==="agent_commission").reduce((s,x)=>s+x.poisha,0);
 const activity=aggregateActivity(snapshot.transactions);
 return Object.freeze({persona:"agent",updatedAt:snapshot.updatedAt,simulation:true,externalSettlementVerified:false,
  transactionsByOperation:operationDistribution(snapshot.transactions),kpis:Object.freeze([
   kpi("float","Fictional e-float",float,"poisha","Not actual float"),
   kpi("commissions","Sample commissions",commissions,"poisha","Not earned or payable"),
   kpi("cash_events","Cash examples",activity.count,"count","No cash handover occurred"),
   kpi("issues","Illustrative review cases",activity.review+activity.failed,"count","Synthetic data"),
  ])});
}
export function merchantDashboard(snapshot:AppSnapshot):DemoDashboard{
 const activity=aggregateActivity(snapshot.transactions),merchantAmount=snapshot.accounts
  .filter(x=>x.kind==="merchant").reduce((s,x)=>s+x.poisha,0);
 return Object.freeze({persona:"merchant",updatedAt:snapshot.updatedAt,simulation:true,externalSettlementVerified:false,
  transactionsByOperation:operationDistribution(snapshot.transactions),kpis:Object.freeze([
   kpi("balance","Fictional merchant balance",merchantAmount,"poisha","Not settled to bank"),
   kpi("volume","Sample transaction volume",activity.sampleValuePoisha,"poisha","Demo only"),
   kpi("events","Sample transaction count",activity.count,"count","Not live customers"),
   kpi("disputes","Sample review items",activity.review,"count","Not real chargebacks"),
  ])});
}
export function dashboardForSnapshot(snapshot:AppSnapshot):DemoDashboard{
 if(!snapshot.simulation)throw new Error("NOT_SIMULATED");
 if(snapshot.actor.role==="agent")return agentDashboard(snapshot);
 if(snapshot.actor.role==="merchant")return merchantDashboard(snapshot);
 return customerDashboard(snapshot);
}
export function dashboardLabels(dashboard:DemoDashboard,locale:Locale):readonly {label:string;value:string;caveat:string}[]{
 return Object.freeze(dashboard.kpis.map(v=>({label:v.label,
  value:v.unit==="poisha"?formatBDT(v.value,locale):v.unit==="basis_points"?`${(v.value/100).toFixed(2)}%`:String(v.value),
  caveat:v.caveat})));
}
export function activitySuccessRate(transactions:readonly SyntheticTransaction[]):number{
 if(transactions.length===0)return 0;
 const successes=transactions.filter(x=>x.state==="completed").length;
 return Math.floor(successes*10_000/transactions.length);
}
export function activityFailureRate(transactions:readonly SyntheticTransaction[]):number{
 if(transactions.length===0)return 0;
 const failures=transactions.filter(x=>x.state==="failed").length;
 return Math.floor(failures*10_000/transactions.length);
}
export function hypotheticalCommissionMix(cashIn:number,cashOut:number,agentCount:number):{total:number;perAgent:number;economicHypothesis:true}{
 if(!Number.isSafeInteger(agentCount)||agentCount<1||agentCount>100_000)throw new Error("INVALID_AGENT_COUNT");
 const total=agentCommissionEstimate(cashIn,cashOut);
 return {total,perAgent:Math.floor(total/agentCount),economicHypothesis:true};
}
export function estimatedLiquidityGap(agents:readonly AgentProfile[],expectedDemand:number):{shortage:number;available:number;sample:true}{
 assertPoisha(expectedDemand);
 const available=agents.filter(x=>x.acceptingRequests).reduce((sum,x)=>sum+assertPoisha(x.cashAvailablePoisha),0);
 return {shortage:Math.max(0,expectedDemand-available),available,sample:true};
}
export function accountConservationHint(accounts:readonly Account[]):{valid:boolean;total:number;unverified:boolean}{
 const all=accounts.every(x=>x.simulation&&x.currency==="BDT"&&Number.isSafeInteger(x.poisha));
 const total=accounts.reduce((sum,x)=>sum+x.poisha,0);
 return {valid:all&&Number.isSafeInteger(total),total,unverified:true};
}
export function syntheticPerformanceSnapshot(snapshots:readonly AppSnapshot[]):{personas:number;accounts:number;transactions:number;realCustomers:0}{
 const personas=new Set(snapshots.map(x=>x.actor.id)).size;
 return {personas,accounts:snapshots.reduce((n,x)=>n+x.accounts.length,0),
  transactions:snapshots.reduce((n,x)=>n+x.transactions.length,0),realCustomers:0};
}
export function noRealDataMetric():Readonly<Record<string,number|boolean>>{
 return Object.freeze({real_active_customers:0,real_revenue_poisha:0,real_settlement_poisha:0,
  verified_regulatory_authorization:false,simulation:true});
}
