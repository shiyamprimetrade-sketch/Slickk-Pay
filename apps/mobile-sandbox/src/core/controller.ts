/** Orchestrates a fictional mobile app. No capability exists to finalize transfers. */
import type {AppSnapshot,Locale,Persona,PaymentDraft,ActorId,UiNetwork,SupportCase,Notification} from "./types.js";
import {sampleSnapshot,fixtureActor} from "./fixtures.js";
import {LocalNavigator,type ScreenName} from "./navigation.js";
import {LocalPreferenceStore,DEFAULT_PREFERENCES,type DisplayPreferences} from "./preferences.js";
import {OfflineWorkspace} from "./offline.js";
import {startDemoSession,lockSession,updateSession,mayViewPrivateFixture,type SessionInfo} from "./security.js";
import {DraftWorkspace,type DraftInput,type DraftReview} from "./drafts.js";
import {createDraft} from "./drafts.js";
import {activityPage,type ActivityFilter} from "./activity.js";
import {LocalPreferenceStore as Preferences} from "./preferences.js";
import {receiptFromTransaction,receiptFromDraft} from "./receipts.js";
import {selectNotices,localMarkRead} from "./notifications.js";
import {prepareSupportDraft,type SupportDraft} from "./support.js";
import {homeModel,type HomeModel} from "./presenters.js";
import {auditPrivateSnapshot} from "./privacy.js";
import type {ReceiptData} from "./types.js";
export type AppEvent={readonly kind:"persona";readonly persona:Persona}|
 {readonly kind:"locale";readonly locale:Locale}|
 {readonly kind:"network";readonly network:UiNetwork}|
 {readonly kind:"navigate";readonly screen:ScreenName}|
 {readonly kind:"back"}|
 {readonly kind:"lock"};
export interface MobileState {
 readonly snapshot:AppSnapshot;
 readonly preferences:DisplayPreferences;
 readonly screen:ScreenName;
 readonly session:SessionInfo;
 readonly network:UiNetwork;
 readonly revision:number;
 readonly locked:boolean;
 readonly simulator:true;
 readonly canMoveMoney:false;
}
export class MobileControllerError extends Error{constructor(readonly code:string){super(code);this.name="MobileControllerError";}}
export class MobileLabController {
 private readonly preferences=new LocalPreferenceStore(DEFAULT_PREFERENCES);
 private nav=new LocalNavigator("customer");
 private readonly offline=new OfflineWorkspace();
 private session:SessionInfo;
 private snapshotData:AppSnapshot;
 private workspace:DraftWorkspace;
 private readonly localCases:SupportDraft[]=[];
 private readonly noticeChanges=new Map<string,Notification>();
 private network:UiNetwork="offline";
 private revision=0;
 private observers=new Set<(state:MobileState)=>void>();
 constructor(now:number=Date.now()){
  const actor=fixtureActor("customer");
  this.snapshotData=sampleSnapshot("customer","bn");
  this.session=startDemoSession("customer",actor.id,now);
  this.workspace=new DraftWorkspace(actor.id);
  if(auditPrivateSnapshot(this.snapshotData).length)throw new MobileControllerError("UNSAFE_FIXTURES");
 }
 state(now:number=Date.now()):MobileState{
  const locked=this.session.locked||now>=this.session.expiresAt;
  return Object.freeze({snapshot:this.snapshotData,preferences:this.preferences.snapshot(),
   screen:this.nav.current().name,session:this.session,network:this.network,revision:this.revision,
   locked,simulator:true,canMoveMoney:false});
 }
 subscribe(callback:(state:MobileState)=>void):()=>void{
  this.observers.add(callback);callback(this.state());
  return ()=>{this.observers.delete(callback);};
 }
 private changed():void{this.revision++;const s=this.state();this.observers.forEach(callback=>callback(s));}
 private requireUnblocked():void{if(this.state().locked)throw new MobileControllerError("SESSION_LOCKED");}
 dispatch(event:AppEvent,now=Date.now()):MobileState{
  const at=new Date(now).toISOString();
  if(event.kind==="persona"){
   const actor=fixtureActor(event.persona);
   this.snapshotData=sampleSnapshot(event.persona,this.preferences.snapshot().locale);
   this.preferences.update({persona:event.persona},at);
   this.nav=new LocalNavigator(event.persona);
   this.session=startDemoSession(event.persona,actor.id,now);
   this.workspace=new DraftWorkspace(actor.id);
   this.localCases.length=0;
   this.noticeChanges.clear();
   this.offline.clear();
  }else if(event.kind==="locale"){
   this.preferences.update({locale:event.locale},at);
   this.snapshotData=sampleSnapshot(this.preferences.snapshot().persona,event.locale);
   this.noticeChanges.clear();
  }else if(event.kind==="network"){
   this.network=event.network;
   this.offline.setNetwork(event.network,at);
  }else if(event.kind==="navigate"){
   this.requireUnblocked();
   this.nav.push(event.screen);
  }else if(event.kind==="back"){
   this.nav.back();
  }else if(event.kind==="lock"){
   this.session=lockSession(this.session);
  }
  this.changed();return this.state(now);
 }
 touch(now=Date.now()):MobileState{
  this.session=updateSession(this.session,now);this.changed();return this.state(now);
 }
 unlock(now=Date.now(),explicitDemoConsent=false):MobileState{
  if(!explicitDemoConsent)throw new MobileControllerError("CONSENT_REQUIRED");
  this.session=startDemoSession(this.snapshotData.actor.role,this.snapshotData.actor.id,now);
  this.changed();return this.state(now);
 }
 dashboard():HomeModel{this.requireUnblocked();return homeModel(this.snapshotData,this.preferences.snapshot().locale);}
 activity(filter:ActivityFilter={}):ReturnType<typeof activityPage>{
  this.requireUnblocked();return activityPage(this.snapshotData.transactions,this.snapshotData.actor.id,filter);
 }
 notices():readonly Notification[]{
  this.requireUnblocked();
  return selectNotices(this.snapshotData.notices.map(x=>this.noticeChanges.get(x.id)??x),this.snapshotData.actor.id);
 }
 markNoticeRead(id:string,now=new Date().toISOString()):void{
  this.requireUnblocked();
  const notice=this.notices().find(x=>x.id===id);if(!notice)throw new MobileControllerError("NOTICE_NOT_FOUND");
  this.noticeChanges.set(id,localMarkRead(notice,now));this.changed();
 }
 newDraft(input:Omit<DraftInput,"ownerId">,now=new Date().toISOString()):PaymentDraft{
  this.requireUnblocked();
  const item=this.workspace.create({...input,ownerId:this.snapshotData.actor.id},now);
  this.changed();return item;
 }
 quoteDraft(id:string,now=new Date().toISOString()):PaymentDraft{
  this.requireUnblocked();const item=this.workspace.update(id,"quote",now);this.changed();return item;
 }
 reviewDraft(id:string,consent:boolean,now=new Date().toISOString()):DraftReview{
  this.requireUnblocked();const result=this.workspace.review(id,now,consent);this.changed();return result;
 }
 cancelDraft(id:string,now=new Date().toISOString()):PaymentDraft{
  this.requireUnblocked();const result=this.workspace.update(id,"cancel",now);this.changed();return result;
 }
 drafts():readonly PaymentDraft[]{this.requireUnblocked();return this.workspace.list();}
 receiptFromSample(id:string):ReceiptData{
  this.requireUnblocked();
  const tx=this.snapshotData.transactions.find(x=>x.id===id);
  if(!tx)throw new MobileControllerError("TRANSACTION_NOT_FOUND");
  return receiptFromTransaction(tx,{locale:this.preferences.snapshot().locale});
 }
 receiptFromDraftId(id:string):ReceiptData{
  this.requireUnblocked();return receiptFromDraft(this.workspace.get(id),this.preferences.snapshot().locale);
 }
 prepareCase(input:Record<string,unknown>,now=new Date().toISOString()):SupportDraft{
  this.requireUnblocked();const result=prepareSupportDraft(this.snapshotData.actor.id,input,now);
  if(!result.ok)throw new MobileControllerError(result.issues[0]?.code??"INVALID_CASE");
  this.localCases.push(result.value);this.changed();return result.value;
 }
 cases():readonly SupportDraft[]{this.requireUnblocked();return Object.freeze([...this.localCases]);}
 cannotSendMoney():never{throw new MobileControllerError("SERVER_AUTHORITY_ABSENT");}
 canViewLocalFixtures(now=Date.now()):boolean{
  return mayViewPrivateFixture(this.session,{appForeground:true,screenProtected:true,hasTrustedLocalClock:true,
   network:this.network,securityNoticeAcknowledged:true},now).enabled;
 }
 sampleAccountBalance():number{
  this.requireUnblocked();return this.snapshotData.accounts.reduce((v,x)=>v+x.poisha,0);
 }
 switchAccountAndWipe(persona:Persona,now=Date.now()):void{
  this.dispatch({kind:"persona",persona},now);
 }
 diagnostics():Readonly<Record<string,string|number|boolean>>{
  return Object.freeze({role:this.snapshotData.actor.role,revision:this.revision,
   accounts:this.snapshotData.accounts.length,fixtures:this.snapshotData.transactions.length,
   localDrafts:this.workspace.list().length,notices:this.snapshotData.notices.length,
   platform:"React Native lab",postingEnabled:false,bankConnected:false});
 }
 clearSensitiveView():void{this.session=lockSession(this.session);this.nav.home();this.changed();}
}
export function createMobileLab(now:number=Date.now()):MobileLabController{return new MobileLabController(now);}
export function neverSubmitActualPayment(_state:MobileState):false{return false;}
