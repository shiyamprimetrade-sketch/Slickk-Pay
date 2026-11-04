/** Non-settling agent workbench combines quote, cash preview, and data trust. */
import {failure,invariant} from "./errors.js";
import {poisha,safeSubtract,type Poisha,moneyLabel} from "./money.js";
import type {AgentPreview} from "./directory.js";
import type {SampleQuote} from "./quotes.js";
import type {CashDialogue,CashChecklist} from "./cash.js";
export interface AgentWorkbench {
 readonly agentId:string;readonly displayLabel:string;
 readonly region:string;readonly quoteTotal:Poisha;
 readonly sampleCashRemaining:Poisha|null;
 readonly sampleCashShortfall:Poisha;
 readonly simulatedReviewCount:number;
 readonly canProvidePhysicalCash:false;
 readonly canPostElectronicFloat:false;
 readonly simulation:true;
}
export function prepareAgentWorkbench(agent:AgentPreview,quote:SampleQuote,
 dialogue:CashDialogue|null,checklist:CashChecklist|null):AgentWorkbench{
 if(quote.operation!=="cash_in"&&quote.operation!=="cash_out")throw failure("INVALID_INPUT");
 if(quote.counterpart!==agent.id&&quote.owner!==agent.id)throw failure("ROLE_FORBIDDEN");
 if(dialogue && dialogue.agent!==agent.id)throw failure("ROLE_FORBIDDEN");
 if(checklist && checklist.agent!==agent.id)throw failure("ROLE_FORBIDDEN");
 const required=quote.principal;
 const shortfall=required>agent.sampleCash?safeSubtract(required,agent.sampleCash):poisha(0,true);
 const remaining=required>agent.sampleCash?null:safeSubtract(agent.sampleCash,required);
 return Object.freeze({agentId:agent.id,displayLabel:agent.label,region:agent.region,
  quoteTotal:quote.total,sampleCashRemaining:remaining,sampleCashShortfall:shortfall,
  simulatedReviewCount:dialogue?Number(dialogue.customerReviewed)+Number(dialogue.agentReviewed):0,
  canProvidePhysicalCash:false,canPostElectronicFloat:false,simulation:true});
}
export function agentWorkbenchWarnings(workbench:AgentWorkbench,locale:"en"|"bn"):readonly string[]{
 const warnings=locale==="bn"?
  ["বাস্তব এজেন্টের নিবন্ধন যাচাই করা হয়নি","ফ্লোট ও নগদের অঙ্ক কাল্পনিক","গ্রাহকের প্রকৃত পিন কখনো চাইবেন না"]:
  ["Agent registration has not been verified","Float and cash values are fictional","Never request the customer's real PIN"];
 if(workbench.sampleCashShortfall>0)warnings.push(locale==="bn"?
  "নমুনা নগদ অপ্রতুল":"Sample cash is insufficient");
 return Object.freeze(warnings);
}
export function displaySampleAgentEarnings(agent:AgentPreview,locale:"en"|"bn"):string{
 const value=moneyLabel(agent.sampleFloat,locale);
 return locale==="bn"?`কাল্পনিক ই-ফ্লোট ${value}`:`Fictional electronic float ${value}`;
}
export function neverConfirmAgentSettlement(_workbench:AgentWorkbench):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
