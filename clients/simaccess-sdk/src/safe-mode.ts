/** Emergency fail-closed mode independent of network or UI navigation. */
import {failure} from "./errors.js";
import {InMemorySession} from "./session.js";
import {SessionSnapshotCache} from "./cache.js";
import {OfflinePolicy} from "./offline.js";
export type SafetyIncident="backend_claimed_real_money"|"leaked_sensitive_data"|
 "device_compromised"|"untrusted_clock"|"unexpected_origin"|"contract_mismatch";
export interface SafeModeState{
 readonly active:boolean;readonly reason:SafetyIncident|null;
 readonly enteredAt:number|null;readonly requiresExplicitReauthentication:boolean;
 readonly paymentEnabled:false;readonly simulation:true;
}
export class SafeModeController{
 private current:SafeModeState=Object.freeze({active:false,reason:null,enteredAt:null,
  requiresExplicitReauthentication:false,paymentEnabled:false,simulation:true});
 constructor(private readonly session:InMemorySession,
  private readonly cache:SessionSnapshotCache,
  private readonly offline:OfflinePolicy,
  private readonly now:()=>number=()=>Date.now()){}
 enter(reason:SafetyIncident):SafeModeState{
  this.session.notifyUnauthorized();this.cache.afterLogout();this.offline.beforeDeviceSuspend();
  this.current=Object.freeze({active:true,reason,enteredAt:this.now(),
   requiresExplicitReauthentication:true,paymentEnabled:false,simulation:true});
  return this.current;
 }
 state():SafeModeState{return this.current;}
 acknowledge():SafeModeState{
  if(!this.current.active)return this.current;
  this.current=Object.freeze({active:true,reason:this.current.reason,enteredAt:this.current.enteredAt,
   requiresExplicitReauthentication:true,paymentEnabled:false,simulation:true});
  return this.current;
 }
 resetAfterFreshDemoLogin():SafeModeState{
  if(this.session.status()!=="active")throw failure("UNAUTHORIZED");
  this.current=Object.freeze({active:false,reason:null,enteredAt:null,
   requiresExplicitReauthentication:false,paymentEnabled:false,simulation:true});
  return this.current;
 }
 assertAvailable():void{
  if(this.current.active)throw failure("LAB_DISABLED");
 }
 canSendMoney():false{return false;}
 mayOverrideSafeModeLocally():false{return false;}
}
export function safetyIncidentMessage(reason:SafetyIncident,locale:"en"|"bn"):string{
 const en:Record<SafetyIncident,string>={
  backend_claimed_real_money:"Server response unexpectedly claimed real-money capability",
  leaked_sensitive_data:"Sensitive fields appeared in the response",
  device_compromised:"Device protection cannot be trusted",
  untrusted_clock:"A trusted clock is unavailable",
  unexpected_origin:"Local-only server origin changed unexpectedly",
  contract_mismatch:"A response violated the agreed financial safety contract"};
 const bn:Record<SafetyIncident,string>={
  backend_claimed_real_money:"সার্ভার ভুলভাবে বাস্তব লেনদেন দাবি করেছে",
  leaked_sensitive_data:"সংবেদনশীল তথ্য পাওয়া গেছে",
  device_compromised:"ডিভাইসের নিরাপত্তা যাচাই করা যায়নি",
  untrusted_clock:"নির্ভরযোগ্য সময় পাওয়া যাচ্ছে না",
  unexpected_origin:"স্থানীয় সার্ভারের ঠিকানা বদলে গেছে",
  contract_mismatch:"সার্ভারের তথ্য নিরাপত্তা চুক্তি মানেনি"};
 return (locale==="bn"?bn:en)[reason];
}
