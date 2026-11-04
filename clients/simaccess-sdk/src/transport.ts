/** Local-only transport with bounded response parsing and zero automatic financial retries. */
import {failure,fromHttp,LabClientError} from "./errors.js";
import {ensureLocalDescriptor} from "./capabilities.js";
import {parseJson,record,validJsonDepth, noCredentialFields, type JsonRecord} from "./primitives.js";

export type HttpMethod = "GET" | "POST";
export interface TransportRequest {
 readonly method:HttpMethod;
 readonly path:string;
 readonly headers:Readonly<Record<string,string>>;
 readonly body?:unknown;
 readonly timeoutMs?:number;
}
export interface HttpResponse {
 readonly status:number;
 readonly body:string;
 readonly contentType:string;
 readonly redirected:boolean;
 readonly url:string;
}
export interface TransportAdapter {
 readonly send:(url:string,req:TransportRequest)=>Promise<HttpResponse>;
}
export interface RequestAudit {
 readonly method:HttpMethod;
 readonly route:string;
 readonly status:"success"|"failure";
 readonly elapsedMs:number;
 readonly responseCode:number|null;
 readonly simulation:true;
}
export type AuditObserver=(event:RequestAudit)=>void;
const DEFAULT_TIMEOUT=8000;
const DEFAULT_MAX_BODY=131072;
export function safeRelativeRoute(input:string):string{
  if(typeof input!=="string" || !input.startsWith("/lab/v4/") || input.length>512)
    throw failure("CROSS_ORIGIN_BLOCKED");
  if(/\/\.|[#\\]|%2f|%5c|\/\//i.test(input))throw failure("CROSS_ORIGIN_BLOCKED");
  const [pathname,query] = input.split("?");
  if(!pathname || !/^\/lab\/v4\/[A-Za-z0-9_\/-]+$/.test(pathname))throw failure("CROSS_ORIGIN_BLOCKED");
  if(query!==undefined){
   const params=new URLSearchParams(query);
   for(const [key,value] of params){
    if(!/^[a-z][a-z_]{0,40}$/.test(key) || value.length>100)throw failure("CROSS_ORIGIN_BLOCKED");
   }
  }
  return input;
}
export function safeQuery(params:Readonly<Record<string,string|number|boolean|null|undefined>>):string{
 const query=new URLSearchParams();
 for(const [key,value] of Object.entries(params)){
  if(!/^[a-z][a-z_]{0,40}$/.test(key))throw failure("INVALID_INPUT");
  if(value===null||value===undefined)continue;
  const text=String(value);
  if(text.length>90 || /[\r\n]/.test(text))throw failure("INVALID_INPUT");
  query.set(key,text);
 }
 return query.size ? `?${query.toString()}`:"";
}
export class LocalTransport {
 readonly baseURL:string;
 private readonly observers=new Set<AuditObserver>();
 constructor(origin:string,private readonly adapter:TransportAdapter,
  private readonly now:()=>number=()=>Date.now()){
   this.baseURL=ensureLocalDescriptor(origin);
 }
 observe(callback:AuditObserver):()=>void{this.observers.add(callback);return()=>this.observers.delete(callback);}
 private emit(event:RequestAudit):void{
  for(const cb of this.observers){try{cb(event);}catch{ /* Observability cannot mutate transactions. */ }}
 }
 async call(request:TransportRequest):Promise<JsonRecord>{
  const route=safeRelativeRoute(request.path);
  const timeStart=this.now();
  let status:"success"|"failure"="failure";
  let responseCode:number|null=null;
  try{
    const timeout=request.timeoutMs??DEFAULT_TIMEOUT;
    if(!Number.isSafeInteger(timeout)||timeout<200||timeout>30000)throw failure("INVALID_INPUT");
    if(request.method!=="GET" && request.method!=="POST")throw failure("INVALID_INPUT");
    if(request.method==="GET"&&request.body!==undefined)throw failure("INVALID_INPUT");
    const url=this.baseURL+route;
    const serialized=request.body===undefined?null:JSON.stringify(request.body);
    if(serialized!==null && serialized.length>8192)throw failure("BODY_TOO_LARGE");
    const headers=Object.freeze({...request.headers,"Accept":"application/json",
      "Cache-Control":"no-store","X-Sim-Client":"slickk-pay-lab-005",
      ...(serialized===null?{}:{"Content-Type":"application/json"})});
    const next:TransportRequest={method:request.method,path:route,headers,
      ...(request.body===undefined?{}:{body:request.body}),timeoutMs:timeout};
    const reply=await this.adapter.send(url,next);
    responseCode=reply.status;
    if(reply.redirected || !reply.url.startsWith(this.baseURL+"/lab/v4/"))
      throw failure("CROSS_ORIGIN_BLOCKED");
    if(reply.body.length>DEFAULT_MAX_BODY)throw failure("BODY_TOO_LARGE");
    if(!reply.contentType.toLowerCase().startsWith("application/json"))
      throw failure("UNTRUSTED_RESPONSE");
    if(reply.status<200||reply.status>=300){
      const raw=parseJson(reply.body);const obj=record(raw);
      throw fromHttp(reply.status,obj["error"]??obj["code"]);
    }
    const parsed=parseJson(reply.body);
    if(!validJsonDepth(parsed))throw failure("UNTRUSTED_RESPONSE");
    noCredentialFields(parsed);
    const object=record(parsed);
    if(object["simulation"]!==true)throw failure("UNTRUSTED_RESPONSE");
    if(object["real_money"]===true || object["can_move_money"]===true ||
       object["handover_authorized"]===true || object["can_pay"]===true)
      throw failure("UNSAFE_CAPABILITY");
    status="success";
    return object;
  }catch(error){
    if(error instanceof LabClientError)throw error;
    throw failure("NETWORK_UNAVAILABLE");
  }finally{
    this.emit(Object.freeze({method:request.method,route,status,
      elapsedMs:Math.max(0,this.now()-timeStart),responseCode,simulation:true}));
  }
 }
}
export function makeFetchAdapter(fetcher:typeof fetch):TransportAdapter{
 return {send:async(url,request)=>{
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),request.timeoutMs??DEFAULT_TIMEOUT);
  try{
    const init:RequestInit={method:request.method,headers:request.headers,
      redirect:"manual",signal:controller.signal,cache:"no-store",
      ...(request.body===undefined?{}:{body:JSON.stringify(request.body)})};
    const result=await fetcher(url,init);
    return {status:result.status,body:await result.text(),
      contentType:result.headers.get("content-type")??"",redirected:result.redirected,
      url:result.url};
  }finally{clearTimeout(timer);}
 }};
}
export function safeLogEvent(event:RequestAudit):string{
  return `${event.method} ${event.route} ${event.status} ${event.responseCode??"offline"}`;
}
export function neverRetryMutation(request:TransportRequest):boolean{
 return request.method==="POST";
}
export async function guardedGetRetry<T>(perform:()=>Promise<T>,attempts=2):Promise<T>{
 if(!Number.isSafeInteger(attempts)||attempts<1||attempts>3)throw failure("INVALID_INPUT");
 let last:unknown=null;
 for(let attempt=0;attempt<attempts;attempt++){
  try{return await perform();}catch(error){
   last=error;
   if(!(error instanceof LabClientError)||!error.retryable)throw error;
  }
 }
 throw last instanceof Error?last:failure("NETWORK_UNAVAILABLE");
}
