/** Simulated agent directory and liquidity planning; never opens a real cash drawer. */
import type {AgentProfile,Account,AccountId,Locale,MoneyQuote,SyntheticTransaction} from "./types.js";
import {assertPoisha,calculatePilotQuote,formatBDT,multiplyRatio} from "./money.js";
import {safeDisplayLabel} from "./validation.js";
export type AgentService="cash_in"|"cash_out"|"assisted_transfer";
export type AgentAvailability="sample_available"|"sample_unavailable"|"sample_low_cash"|"sample_low_float";
export interface AgentDirectoryOptions {readonly search?:string;readonly cashMinimumPoisha?:number;readonly acceptingOnly?:boolean;readonly limit?:number;}
export interface AgentListRow {readonly id:string;readonly name:string;readonly location:string;readonly status:AgentAvailability;readonly serviceHours:string;readonly simulation:true;}
export function lookupAgent(agents:readonly AgentProfile[],id:string):AgentProfile|null{return agents.find(a=>a.id===id)??null;}
export function checkAgentAvailability(agent:AgentProfile,service:AgentService,amount:number,floatBalance:number):AgentAvailability{
 assertPoisha(amount);assertPoisha(floatBalance);
 if(!agent.acceptingRequests)return "sample_unavailable";
 if(service==="cash_out"&&agent.cashAvailablePoisha<amount)return "sample_low_cash";
 if((service==="cash_in"||service==="assisted_transfer")&&floatBalance<amount)return "sample_low_float";
 return "sample_available";
}
export function directoryAgents(agents:readonly AgentProfile[],options:AgentDirectoryOptions={}):readonly AgentListRow[]{
 const min=options.cashMinimumPoisha??0;assertPoisha(min);
 const limit=options.limit??40;if(!Number.isSafeInteger(limit)||limit<1||limit>100)throw new Error("INVALID_AGENT_LIST_LIMIT");
 const search=(options.search??"").toLocaleLowerCase("en").trim();
 if(search.length>80)throw new Error("SEARCH_TOO_LONG");
 const filtered=agents.filter(a=>a.simulation&&(!options.acceptingOnly||a.acceptingRequests)&&
    a.cashAvailablePoisha>=min&&(a.businessName.toLocaleLowerCase("en").includes(search)||
    a.locationLabel.toLocaleLowerCase("en").includes(search)));
 return Object.freeze(filtered.slice(0,limit).map(a=>Object.freeze({id:a.id,name:safeDisplayLabel(a.businessName),
    location:safeDisplayLabel(a.locationLabel),status:a.acceptingRequests?"sample_available" as const:"sample_unavailable" as const,
    serviceHours:a.serviceHours,simulation:true as const})));
}
export function formatAgentRow(row:AgentListRow,locale:Locale):string{
 const state=row.status==="sample_available"?(locale==="bn"?"নমুনা সক্রিয়":"Sample available"):(locale==="bn"?"নমুনা বন্ধ":"Sample unavailable");
 return `${row.name} · ${row.location} · ${state}`;
}
export interface CashQuotePreview {readonly quote:MoneyQuote;readonly status:AgentAvailability;readonly agentName:string;readonly nonBinding:true;readonly notice:string;}
export function quoteAgentCash(agent:AgentProfile,service:"cash_in"|"cash_out",amount:number,floatBalance:number,expiresAt:string):CashQuotePreview{
 const quote=calculatePilotQuote(service,amount,expiresAt);
 const status=checkAgentAvailability(agent,service,amount,floatBalance);
 return Object.freeze({quote,status,agentName:agent.businessName,nonBinding:true,
  notice:"Fictional funds and physical cash. No reservation or handover was made."});
}
export function sampleAgentFloat(agent:AgentProfile,accounts:readonly Account[]):{floatPoisha:number;commissionPoisha:number;cashPoisha:number;simulation:true}{
 const f=accounts.find(x=>x.id===agent.floatAccountId);
 const c=accounts.find(x=>x.id===agent.commissionAccountId);
 return Object.freeze({floatPoisha:f?.poisha??0,commissionPoisha:c?.poisha??0,
  cashPoisha:agent.cashAvailablePoisha,simulation:true});
}
export interface LiquidityWarning {readonly code:string;readonly explanation:string;readonly severity:"low"|"medium"|"high";}
export function liquidityWarnings(cash:number,float:number,demand:number):readonly LiquidityWarning[]{
 [cash,float,demand].forEach(v=>assertPoisha(v));
 const findings:LiquidityWarning[]=[];
 if(demand>cash)findings.push({code:"CASH_SHORTFALL",explanation:"Illustrative cash inventory is below demand",severity:"high"});
 if(demand>float)findings.push({code:"FLOAT_SHORTFALL",explanation:"Illustrative e-float is below demand",severity:"high"});
 if(demand>0&&cash<demand*2)findings.push({code:"LOW_CASH_BUFFER",explanation:"Illustrative cash buffer is under twice expected demand",severity:"medium"});
 if(demand>0&&float<demand*2)findings.push({code:"LOW_FLOAT_BUFFER",explanation:"Illustrative float buffer is under twice expected demand",severity:"medium"});
 return Object.freeze(findings);
}
export function estimateCashDemand(history:readonly SyntheticTransaction[],days:number):number{
 if(!Number.isSafeInteger(days)||days<1||days>365)throw new Error("INVALID_WINDOW");
 const cashOut=history.filter(x=>x.operation==="cash_out"&&x.state==="completed");
 const total=cashOut.reduce((sum,x)=>sum+assertPoisha(x.amountPoisha),0);
 return multiplyRatio(total,days,Math.max(1,cashOut.length),"ceil");
}
export function agentCommissionEstimate(cashIn:number,cashOut:number,bonus:number=0):number{
 [cashIn,cashOut,bonus].forEach(v=>assertPoisha(v));
 return multiplyRatio(cashIn,150,100_000)+multiplyRatio(cashOut,550,100_000)+bonus;
}
export function agentProfitability(cashIn:number,cashOut:number,transport:number,floatCost:number,staffCost:number):{grossCommission:number;expenses:number;netMargin:number}{
 const gross=agentCommissionEstimate(cashIn,cashOut),expenses=transport+floatCost+staffCost;
 [transport,floatCost,staffCost].forEach(v=>assertPoisha(v));
 return {grossCommission:gross,expenses,netMargin:gross-expenses};
}
export function agentStatusDescription(agent:AgentProfile,locale:Locale):string{
 const label=agent.acceptingRequests?(locale==="bn"?"নমুনা এজেন্ট সক্রিয়":"Sample agent active"):
  (locale==="bn"?"নমুনা এজেন্ট অনুপলব্ধ":"Sample agent unavailable");
 return `${label} · ${formatBDT(agent.cashAvailablePoisha,locale)} ${locale==="bn"?"নমুনা নগদ":"fictional cash"}`;
}
export function cashServiceChecklist(agent:AgentProfile,amount:number):readonly {code:string;passed:boolean}[]{
 assertPoisha(amount,false);
 return Object.freeze([
  {code:"SYNTHETIC_AGENT",passed:agent.id.startsWith("sim_")&&agent.simulation},
  {code:"ACCEPTS_REQUESTS",passed:agent.acceptingRequests},
  {code:"SAMPLE_CASH_CAPACITY",passed:agent.cashAvailablePoisha>=amount},
  {code:"ACTUAL_IDENTITY_VERIFIED",passed:false},
  {code:"REAL_CUSTOMER_AUTHORIZED",passed:false},
  {code:"PHYSICAL_CASH_HANDOVER_VERIFIED",passed:false},
 ]);
}
export function agentDailyOperations(history:readonly SyntheticTransaction[]):{inCount:number;outCount:number;inPoisha:number;outPoisha:number;issues:number}{
 const cash=history.filter(x=>x.operation==="cash_in"||x.operation==="cash_out");
 return cash.reduce((a,x)=>{
  if(x.operation==="cash_in"){a.inCount++;if(x.state==="completed")a.inPoisha+=x.amountPoisha;}
  if(x.operation==="cash_out"){a.outCount++;if(x.state==="completed")a.outPoisha+=x.amountPoisha;}
  if(x.state==="failed"||x.state==="review")a.issues++;
  return a;
 },{inCount:0,outCount:0,inPoisha:0,outPoisha:0,issues:0});
}
export function needsAgentReview(agent:AgentProfile):boolean{return !agent.acceptingRequests||agent.qualityStatus==="sample_review";}
export function agentSearchHint(agents:readonly AgentProfile[]):string{return `${agents.length} synthetic agent locations · not geolocation verified`;}
