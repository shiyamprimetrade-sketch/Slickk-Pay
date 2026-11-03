/** Explainable client-side warning hints; NEVER a lender or financial risk decision. */
import type {RiskFinding,PaymentDraft,AgentProfile,SyntheticTransaction,Account,UiNetwork} from "./types.js";
import {assertPoisha} from "./money.js";
export interface RiskContext {readonly actorId:string;readonly account:Account|null;readonly network:UiNetwork;readonly agent:AgentProfile|null;readonly history:readonly SyntheticTransaction[];readonly now:string;}
export interface RiskAssessment {readonly findings:readonly RiskFinding[];readonly requiresServer:true;readonly blocksLocalSubmission:true;readonly simulation:true;readonly label:"ADVISORY_ONLY";}
function finding(code:string,severity:RiskFinding["severity"],label:string,blocksSubmission:boolean):RiskFinding{
 return Object.freeze({code,severity,label,blocksSubmission});
}
export function assessDraftRisks(draft:PaymentDraft,context:RiskContext):RiskAssessment{
 const findings:RiskFinding[]=[];
 if(!draft.simulation||!draft.ownerId.startsWith("sim_"))findings.push(finding("NOT_SYNTHETIC","critical","Untrusted account reference",true));
 if(draft.ownerId!==context.actorId)findings.push(finding("WRONG_OWNER","critical","Draft owner differs from viewer",true));
 if(context.network==="offline")findings.push(finding("OFFLINE","warning","Offline payments cannot be authorized",true));
 if(context.account?.frozen) findings.push(finding("FROZEN_SAMPLE_ACCOUNT","critical","Account sample is frozen",true));
 if(context.account&&draft.principalPoisha>context.account.poisha)findings.push(finding("SAMPLE_INSUFFICIENT","warning","Sample balance below draft amount",true));
 if(draft.operation==="cash_out"){
  if(!context.agent)findings.push(finding("AGENT_NOT_SELECTED","warning","Sample agent required",true));
  else if(!context.agent.acceptingRequests)findings.push(finding("SAMPLE_AGENT_CLOSED","warning","Sample agent is unavailable",true));
  else if(context.agent.cashAvailablePoisha<draft.principalPoisha)findings.push(finding("SAMPLE_CASH_SHORT","warning","Example cash inventory too low",true));
 }
 if(draft.principalPoisha>=2_500_000)findings.push(finding("HIGH_SAMPLE_AMOUNT","info","Manual review likely needed in a real system",false));
 const now=Date.parse(context.now);
 if(!Number.isFinite(now))findings.push(finding("CLOCK_INVALID","critical","Device clock cannot be trusted",true));
 const recent=context.history.filter(x=>x.ownerId===context.actorId&&now-Date.parse(x.occurredAt)<3600_000&&now>=Date.parse(x.occurredAt));
 if(recent.length>=10)findings.push(finding("SAMPLE_HIGH_VELOCITY","warning","Many recent fictional transactions",true));
 const newIds=new Set(context.history.map(x=>x.reference));
 if(newIds.size!==context.history.length)findings.push(finding("SAMPLE_REPLAY","critical","Duplicate fictional references",true));
 return Object.freeze({findings:Object.freeze(findings),requiresServer:true,blocksLocalSubmission:true,simulation:true,label:"ADVISORY_ONLY"});
}
export function riskSeverityRank(severity:RiskFinding["severity"]):number{
 return severity==="critical"?3:severity==="warning"?2:1;
}
export function orderRiskFindings(findings:readonly RiskFinding[]):readonly RiskFinding[]{
 return Object.freeze([...findings].sort((a,b)=>riskSeverityRank(b.severity)-riskSeverityRank(a.severity)||a.code.localeCompare(b.code)));
}
export function riskSummary(assessment:RiskAssessment):{critical:number;warnings:number;info:number;mayAuthorize:false}{
 return {critical:assessment.findings.filter(x=>x.severity==="critical").length,
  warnings:assessment.findings.filter(x=>x.severity==="warning").length,
  info:assessment.findings.filter(x=>x.severity==="info").length,mayAuthorize:false};
}
export function suspiciousAgentPatterns(transactions:readonly SyntheticTransaction[],agentId:string):readonly RiskFinding[]{
 const agentTx=transactions.filter(x=>x.ownerId===agentId&&x.simulation);
 const findings:RiskFinding[]=[];
 const refs=new Set<string>();
 for(const tx of agentTx){
  if(refs.has(tx.reference))findings.push(finding("DUPLICATE_AGENT_REFERENCE","critical","Duplicate sample transaction reference",true));
  refs.add(tx.reference);
 }
 const failed=agentTx.filter(x=>x.state==="failed").length;
 if(agentTx.length>=5&&failed*2>=agentTx.length)findings.push(finding("SAMPLE_FAILURE_CLUSTER","warning","High illustrative failed-operation share",true));
 const amounts=agentTx.filter(x=>x.operation==="cash_out").map(x=>x.amountPoisha);
 if(amounts.length>=3&&amounts.every(x=>x>=1_000_000))findings.push(finding("REPEATED_LARGE_WITHDRAWALS","warning","Example repeated high-value cash outs",true));
 return orderRiskFindings(findings);
}
export function concentrationRisk(amounts:readonly number[]):{largestShareBp:number;total:number;overHalf:boolean}{
 amounts.forEach(x=>assertPoisha(x));
 const total=amounts.reduce((a,b)=>a+b,0);assertPoisha(total);
 const largest=amounts.length?Math.max(...amounts):0;
 const largestShareBp=total===0?0:Math.floor(largest*10_000/total);
 return {largestShareBp,total,overHalf:largestShareBp>5000};
}
export function deviceRiskFlags(context:{rootedUnknown:boolean;screenUnlocked:boolean;debugBuild:boolean;clockDriftMs:number;secureStorageAvailable:boolean}):readonly RiskFinding[]{
 const warnings:RiskFinding[]=[];
 if(context.rootedUnknown)warnings.push(finding("DEVICE_INTEGRITY_UNKNOWN","warning","Device integrity not verified",true));
 if(!context.screenUnlocked)warnings.push(finding("SCREEN_UNLOCK_MISSING","warning","No local screen protection",true));
 if(context.debugBuild)warnings.push(finding("DEVELOPMENT_BUILD","info","Debug build cannot process real money",true));
 if(!Number.isFinite(context.clockDriftMs)||Math.abs(context.clockDriftMs)>120_000)warnings.push(finding("CLOCK_DRIFT","warning","Device clock drift",true));
 if(!context.secureStorageAvailable)warnings.push(finding("NO_SECURE_KEYSTORE","critical","Secure storage unavailable",true));
 return orderRiskFindings(warnings);
}
export function riskDisclaimer():string{return "Explanations are synthetic hints, not fraud adjudication, underwriting, or regulatory clearance.";}
export function riskFeedDisabled():{automaticDecline:false;automaticDisbursement:false;manualReviewRequired:true}{
 return {automaticDecline:false,automaticDisbursement:false,manualReviewRequired:true};
}
export function limitPreview(amount:number,limit:number,currentSpent:number):{within:boolean;remaining:number;blockedReason:string|null}{
 [amount,limit,currentSpent].forEach(x=>assertPoisha(x));
 const remaining=Math.max(0,limit-currentSpent);
 return {within:amount<=remaining,remaining,blockedReason:amount>remaining?"SAMPLE_LIMIT_EXCEEDED":null};
}
export function accountRiskIndicators(account:Account):readonly RiskFinding[]{
 const problems:RiskFinding[]=[];
 if(!account.simulation)problems.push(finding("UNVERIFIED_ACCOUNT","critical","Account is not a fictional fixture",true));
 if(account.frozen)problems.push(finding("FROZEN_ACCOUNT","critical","Sample account is frozen",true));
 if(!Number.isSafeInteger(account.poisha)||account.poisha<0)problems.push(finding("INVALID_BALANCE","critical","Invalid sample balance",true));
 if(account.version<0)problems.push(finding("INVALID_VERSION","warning","Inconsistent account revision",true));
 return Object.freeze(problems);
}
