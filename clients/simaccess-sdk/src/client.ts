/** Typed client for Cycle 004 loopback-only synthetic customer/agent API.
 * All state changes are sample previews. No ledger mutation routes exist here.
 */
import {failure,invariant,LabClientError} from "./errors.js";
import {type TransportRequest,LocalTransport,safeQuery,guardedGetRetry} from "./transport.js";
import {InMemorySession,parseSessionCreated,type SessionView} from "./session.js";
import {type ActorId,type DeviceId,syntheticId,syntheticDevice} from "./identity.js";
import {record,required,text,integer} from "./primitives.js";
import {capabilities,health,type SandboxCapabilities,type HealthView} from "./capabilities.js";
import {parseQuote,parseQuoteList,validateNewQuoteInput,type SampleQuote,type NewQuoteInput} from "./quotes.js";
import {parseReview,parseRequestList,type ReviewedPreview} from "./requests.js";
import {parseDirectory,validateDirectorySearch,type DirectorySearch,type AgentResult} from "./directory.js";
import {parseReceipt,type PreviewReceipt} from "./receipts.js";
import {parseChecklist,parseDialogue,safeChecklistPatch,validateAcknowledgementReference,
 type CashChecklist,type CashDialogue,type CashChecklistUpdate} from "./cash.js";
import {parseSupportCase,parseSupportList,validateSupportDraft,
 type SupportCategory,type SupportCase} from "./support.js";
import {parseQrIssue,parseQrInspection,validateSampleQrUri,
 type SampleQr,type QrDetails} from "./qr.js";
import {parseNotices,type Notice} from "./notices.js";
import {queryActivity,parseActivityPage,type ActivityQuery,type ActivityRow} from "./activity.js";
import {SessionSnapshotCache} from "./cache.js";

export interface SessionStart {
 readonly actor_id:ActorId;readonly device_id:DeviceId;readonly demo_pin:string;
}
export interface ClientConfig {
 readonly transport:LocalTransport;
 readonly session:InMemorySession;
 readonly cache:SessionSnapshotCache;
 readonly nowSeconds:()=>number;
}
export class SyntheticAccessClient {
 readonly simulation=true as const;
 readonly canMoveMoney=false as const;
 constructor(private readonly config:ClientConfig){}
 private requestHttp(method:"GET"|"POST",path:string,body?:unknown,
  authenticated=true):Promise<Readonly<Record<string,unknown>>>{
   const send=(headers:Readonly<Record<string,string>>)=>{
    const spec:TransportRequest={method,path,headers,
      ...(body===undefined?{}:{body}),timeoutMs:8000};
    return this.config.transport.call(spec);
   };
   if(!authenticated)return send({});
   return this.config.session.withTransientHeaders(send);
 }
 private read(path:string,category?:string):Promise<Readonly<Record<string,unknown>>>{
  return guardedGetRetry(()=>this.requestHttp("GET",path)).then(value=>{
   if(category)this.config.cache.save(category,value);
   return value;
  });
 }
 async health():Promise<HealthView>{return health(await this.requestHttp("GET","/lab/v4/health",undefined,false));}
 async capabilities():Promise<SandboxCapabilities>{
  return capabilities(await this.requestHttp("GET","/lab/v4/capabilities",undefined,false));
 }
 async startSession(input:SessionStart):Promise<SessionView>{
  syntheticId(input.actor_id);syntheticDevice(input.device_id);
  text(input.demo_pin,8,128);
  this.config.session.wipe();
  this.config.cache.afterLogout();
  const raw=await this.requestHttp("POST","/lab/v4/session",input,false);
  const created=parseSessionCreated(raw);
  invariant(created.actor===input.actor_id,"UNTRUSTED_RESPONSE");
  this.config.cache.bindActor(created.actor);
  return this.config.session.attach(created,input.device_id);
 }
 async endSession():Promise<void>{
  try{await this.requestHttp("POST","/lab/v4/logout");}
  finally{this.config.session.logoutLocal();this.config.cache.afterLogout();}
 }
 private own():ActorId{return this.config.session.view().actor;}
 async profile():Promise<Readonly<Record<string,unknown>>>{
  const raw=await this.read("/lab/v4/me","profile");
  invariant(raw["simulation"]===true,"UNTRUSTED_RESPONSE");
  return raw;
 }
 async activity(query:ActivityQuery={limit:40}):Promise<readonly ActivityRow[]>{
  const params=queryActivity(query);
  const path="/lab/v4/activity/search"+safeQuery(params);
  const data=await this.read(path,"activity");
  return parseActivityPage(data,this.own());
 }
 async agents(query:DirectorySearch={}):Promise<AgentResult>{
  validateDirectorySearch(query);
  const parameters:Record<string,string|number>={};
  if(query.region)parameters["region"]=query.region;
  const path="/lab/v4/agents"+safeQuery(parameters);
  return parseDirectory(await this.read(path,"agents"));
 }
 async newQuote(input:NewQuoteInput):Promise<SampleQuote>{
  validateNewQuoteInput(input);
  if(input.counterpart_id===this.own())throw failure("INVALID_INPUT");
  const raw=await this.requestHttp("POST","/lab/v4/quotes",input);
  const quote=parseQuote(raw);
  invariant(quote.owner===this.own()&&quote.operation===input.operation&&
   quote.counterpart===input.counterpart_id&&quote.principal===input.principal_poisha,
   "UNTRUSTED_RESPONSE");
  this.config.cache.clearCategory("quotes");
  return quote;
 }
 async quotes():Promise<readonly SampleQuote[]>{
  const raw=await this.read("/lab/v4/quotes","quotes");
  const result=parseQuoteList(raw);
  if(result.some(item=>item.owner!==this.own()))throw failure("ROLE_FORBIDDEN");
  return result;
 }
 async quote(id:ActorId):Promise<SampleQuote>{
  const raw=await this.read(`/lab/v4/quotes/${syntheticId(id)}`);
  const quote=parseQuote(raw);
  if(quote.owner!==this.own())throw failure("ROLE_FORBIDDEN");
  return quote;
 }
 async cancelQuote(id:ActorId):Promise<SampleQuote>{
  const raw=await this.requestHttp("POST",`/lab/v4/quotes/${syntheticId(id)}/cancel`);
  const quote=parseQuote(raw);
  if(quote.owner!==this.own()||quote.status!=="cancelled")throw failure("UNTRUSTED_RESPONSE");
  this.config.cache.clearCategory("quotes");
  return quote;
 }
 async reviewQuote(id:ActorId):Promise<ReviewedPreview>{
  const raw=await this.requestHttp("POST",`/lab/v4/quotes/${syntheticId(id)}/review`,
   {explicit_preview_consent:true});
  const review=parseReview(raw);
  if(review.owner!==this.own()||review.quoteId!==id)throw failure("ROLE_FORBIDDEN");
  this.config.cache.clearCategory("quotes");
  this.config.cache.clearCategory("requests");
  return review;
 }
 async requests():Promise<readonly ReviewedPreview[]>{
  const raw=await this.read("/lab/v4/requests","requests");
  const values=parseRequestList(raw);
  if(values.some(value=>value.owner!==this.own()))throw failure("ROLE_FORBIDDEN");
  return values;
 }
 async request(id:ActorId):Promise<ReviewedPreview>{
  const value=parseReview(await this.read(`/lab/v4/requests/${syntheticId(id)}`));
  if(value.owner!==this.own())throw failure("ROLE_FORBIDDEN");
  return value;
 }
 async cancelRequest(id:ActorId):Promise<ReviewedPreview>{
  const value=parseReview(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cancel`));
  if(value.owner!==this.own()||value.status!=="cancelled")throw failure("UNTRUSTED_RESPONSE");
  this.config.cache.clearCategory("requests");
  return value;
 }
 async receipt(id:ActorId,locale:"en"|"bn"="en"):Promise<PreviewReceipt>{
  const raw=await this.read(`/lab/v4/requests/${syntheticId(id)}/receipt`+safeQuery({locale}));
  const result=parseReceipt(raw);
  if(result.requestId!==id)throw failure("UNTRUSTED_RESPONSE");
  return result;
 }
 async createCashChecklist(id:ActorId):Promise<CashChecklist>{
  return parseChecklist(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cash-checklist`));
 }
 async updateCashChecklist(id:ActorId,update:CashChecklistUpdate):Promise<CashChecklist>{
  return parseChecklist(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cash-checklist/update`,
   safeChecklistPatch(update)));
 }
 async startCashReview(id:ActorId):Promise<CashDialogue>{
  return parseDialogue(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cash-dialogue`));
 }
 async cashReview(id:ActorId):Promise<CashDialogue>{
  return parseDialogue(await this.read(`/lab/v4/requests/${syntheticId(id)}/cash-dialogue`));
 }
 async acknowledgeCashReview(id:ActorId,reference:string):Promise<CashDialogue>{
  const review_reference=validateAcknowledgementReference(reference);
  return parseDialogue(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cash-dialogue/ack`,
   {review_reference}));
 }
 async cancelCashReview(id:ActorId):Promise<CashDialogue>{
  return parseDialogue(await this.requestHttp("POST",`/lab/v4/requests/${syntheticId(id)}/cash-dialogue/cancel`));
 }
 async supportDraft(category:SupportCategory,description:string):Promise<SupportCase>{
  const input=validateSupportDraft(category,description);
  const value=parseSupportCase(await this.requestHttp("POST","/lab/v4/support",input),this.own());
  if(value.owner!==this.own())throw failure("ROLE_FORBIDDEN");
  return value;
 }
 async supportCases():Promise<readonly SupportCase[]>{
  const cases=parseSupportList(await this.read("/lab/v4/support"),this.own());
  if(cases.some(item=>item.owner!==this.own()))throw failure("ROLE_FORBIDDEN");
  return cases;
 }
 async issueSampleQr(recipient_id:ActorId,operation:"transfer"|"merchant_payment",
  amount_poisha:number):Promise<SampleQr>{
  syntheticId(recipient_id);integer(amount_poisha,1,50_000_000);
  return parseQrIssue(await this.requestHttp("POST","/lab/v4/qr",{
   recipient_id,operation,amount_poisha,lifetime:120}));
 }
 async inspectQr(uri:string):Promise<QrDetails>{
  return parseQrInspection(await this.requestHttp("POST","/lab/v4/qr/inspect",
   {uri:validateSampleQrUri(uri)}));
 }
 async notices():Promise<readonly Notice[]>{return parseNotices(await this.read("/lab/v4/notifications"));}
 snapshotCategory<T>(category:string):T|null{return this.config.cache.read<T>(category).data;}
 lock():void{this.config.session.beforeBackground();this.config.cache.beforeBackground();}
 clear():void{this.config.session.wipe();this.config.cache.afterLogout();}
 mayExecutePayment():false{return false;}
 mayAuthorizeCash():false{return false;}
 executePayment():never{throw failure("SERVER_AUTHORITY_ABSENT");}
 confirmBankSettlement():never{throw failure("SERVER_AUTHORITY_ABSENT");}
 disburseLoan():never{throw failure("SERVER_AUTHORITY_ABSENT");}
}
