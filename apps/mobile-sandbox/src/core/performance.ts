/** Deterministic low-end-device resource budgets for preview-only screens. */
export interface ResourceBudget {readonly maxRows:number;readonly maxBytes:number;readonly maxCachedPages:number;readonly maxDrafts:number;
 readonly animationEnabled:boolean;readonly mediaAutoFetch:false;readonly paymentCaching:false;}
export interface DeviceBudgetContext {readonly memoryClass:"low"|"standard";readonly network:"offline"|"limited"|"online";readonly batteryLow:boolean;readonly reduceMotion:boolean;}
export function chooseResourceBudget(context:DeviceBudgetContext):ResourceBudget{
 const constrained=context.memoryClass==="low"||context.batteryLow;
 return Object.freeze({maxRows:constrained?12:40,maxBytes:constrained?128_000:512_000,
  maxCachedPages:constrained?1:3,maxDrafts:constrained?3:10,
  animationEnabled:!constrained&&!context.reduceMotion,mediaAutoFetch:false,paymentCaching:false});
}
export interface RenderingSlice<T> {readonly visible:readonly T[];readonly total:number;readonly truncated:boolean;readonly start:number;}
export function windowRows<T>(items:readonly T[],start:number,budget:ResourceBudget):RenderingSlice<T>{
 if(!Number.isSafeInteger(start)||start<0)throw new Error("INVALID_WINDOW_OFFSET");
 return Object.freeze({visible:Object.freeze(items.slice(start,start+budget.maxRows)),total:items.length,
  truncated:start+budget.maxRows<items.length,start});
}
export function estimateJsonBytes(value:unknown):number{
 const str=JSON.stringify(value);
 if(str===undefined)throw new Error("UNSERIALIZABLE");
 return new TextEncoder().encode(str).byteLength;
}
export function respectResponseBudget(value:unknown,budget:ResourceBudget):boolean{
 return estimateJsonBytes(value)<=budget.maxBytes;
}
export function performanceChecklist():readonly {name:string;testedOnDevice:boolean;enforcedByCore:boolean}[]{
 return Object.freeze([
  {name:"Small render windows",testedOnDevice:false,enforcedByCore:true},
  {name:"No automatic media downloads",testedOnDevice:false,enforcedByCore:true},
  {name:"Bounded response parsing",testedOnDevice:false,enforcedByCore:true},
  {name:"No persisted balances",testedOnDevice:false,enforcedByCore:true},
  {name:"Actual Android jank profiling",testedOnDevice:false,enforcedByCore:false},
  {name:"Real battery measurement",testedOnDevice:false,enforcedByCore:false},
 ]);
}
export function safePagingStart(page:number,pageSize:number):number{
 if(!Number.isSafeInteger(page)||page<1||page>100_000||!Number.isSafeInteger(pageSize)||pageSize<1||pageSize>100)throw new Error("INVALID_PAGING");
 return (page-1)*pageSize;
}
export function lowEndDeviceMemoryPlan():Readonly<Record<string,string|boolean>>{
 return Object.freeze({autoMediaDownload:false,offlineAuthoritativeBalance:false,
  backgroundFinancialPosting:false,preferredActivityPageSize:"12",reliableServerSync:"not_implemented"});
}
