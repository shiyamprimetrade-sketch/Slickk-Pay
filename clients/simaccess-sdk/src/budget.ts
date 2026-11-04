/** Low-cost Android memory/network budget gates for synthetic read-only views. */
import {failure,invariant} from "./errors.js";
export interface DeviceBudget{
 readonly maxResponseBytes:number;readonly maxListRows:number;
 readonly maxCachedSnapshots:number;readonly maxRequestDurationMs:number;
 readonly maxActiveSubscriptions:number;readonly allowPersistentTokens:false;
 readonly allowOfflineFinancialPosts:false;
}
export const LOW_END_ANDROID_BUDGET:DeviceBudget=Object.freeze({
 maxResponseBytes:131072,maxListRows:100,maxCachedSnapshots:50,
 maxRequestDurationMs:8000,maxActiveSubscriptions:10,
 allowPersistentTokens:false,allowOfflineFinancialPosts:false
});
export interface BudgetUse{
 readonly responseBytes:number;readonly listRows:number;
 readonly cachedSnapshots:number;readonly requestDurationMs:number;
 readonly activeSubscriptions:number;
}
export interface BudgetFinding{
 readonly withinBudget:boolean;readonly exceeded:readonly (keyof BudgetUse)[];
 readonly nextAction:"render"|"degrade";readonly simulation:true;
}
export function inspectBudget(use:BudgetUse,budget:DeviceBudget=LOW_END_ANDROID_BUDGET):BudgetFinding{
 const allowed:Readonly<Record<keyof BudgetUse,number>>={
  responseBytes:budget.maxResponseBytes,listRows:budget.maxListRows,
  cachedSnapshots:budget.maxCachedSnapshots,requestDurationMs:budget.maxRequestDurationMs,
  activeSubscriptions:budget.maxActiveSubscriptions};
 const exceeded:(keyof BudgetUse)[]=[];
 for(const key of Object.keys(allowed) as (keyof BudgetUse)[]){
  const current=use[key];
  if(!Number.isSafeInteger(current)||current<0)throw failure("INVALID_INPUT");
  if(current>allowed[key])exceeded.push(key);
 }
 return Object.freeze({withinBudget:exceeded.length===0,exceeded:Object.freeze(exceeded),
  nextAction:exceeded.length?"degrade":"render",simulation:true});
}
export function compactList<T>(items:readonly T[],budget:DeviceBudget=LOW_END_ANDROID_BUDGET):readonly T[]{
 return Object.freeze(items.slice(0,budget.maxListRows));
}
export function shouldRenderStaleBadge(ageSeconds:number):boolean{
 if(!Number.isSafeInteger(ageSeconds)||ageSeconds<0)throw failure("INVALID_INPUT");
 return ageSeconds>60;
}
export function memoryPressurePolicy(level:"low"|"moderate"|"critical"):
 Readonly<{dropCaches:boolean;lockSession:boolean;continueBackgroundSync:false}>{
 return Object.freeze({dropCaches:level!=="low",lockSession:level==="critical",
  continueBackgroundSync:false});
}
export function cannotIncreaseBudgetForPayments(_budget:DeviceBudget):false{return false;}
