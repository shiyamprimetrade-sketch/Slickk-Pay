/** Preserve simulation warnings through navigation, screenshots and accessibility. */
import {failure} from "./errors.js";
import type {DisplayCard,Locale} from "./presenters.js";
export interface Announcement{
 readonly text:string;readonly priority:"polite"|"assertive";
 readonly role:"status"|"alert";readonly simulation:true;
}
export interface ViewIntegrity{
 readonly hasSimulationWarning:boolean;
 readonly hasNoMoneyControls:boolean;
 readonly touchTargetMinimum:number;
 readonly shouldHideScreenshotSecrets:true;
 readonly safe:boolean;
}
export function buildAnnouncement(card:DisplayCard,locale:Locale):Announcement{
 const prefix=locale==="bn"?"স্লিক পে ডেমো":"Slickk Pay simulation";
 return Object.freeze({text:`${prefix}. ${card.title}. ${card.warning}.`,
  priority:"assertive",role:"alert",simulation:true});
}
export function inspectCard(card:DisplayCard):ViewIntegrity{
 const warning=card.warning.trim().length>6;
 const noMoney=card.canSubmitMoney===false && card.simulation===true;
 return Object.freeze({hasSimulationWarning:warning,hasNoMoneyControls:noMoney,
  touchTargetMinimum:44,shouldHideScreenshotSecrets:true,safe:warning&&noMoney});
}
export function requireSafeCard(card:DisplayCard):void{
 if(!inspectCard(card).safe)throw failure("UNSAFE_CAPABILITY");
}
export interface AccessibleAction{
 readonly title:string;readonly hint:string;
 readonly enabled:boolean;readonly financialAuthorization:false;
 readonly minTargetDp:number;
}
export function previewAction(label:string,locale:Locale,enabled:boolean):AccessibleAction{
 return Object.freeze({title:label,
  hint:locale==="bn"?"শুধু নমুনা পর্যালোচনা, অর্থ যাবে না":"Preview only; money will not move",
  enabled,financialAuthorization:false,minTargetDp:48});
}
export function forbiddenCashAction(locale:Locale):AccessibleAction{
 return Object.freeze({title:locale==="bn"?"নগদ দেওয়া যাবে না":"Cash delivery unavailable",
  hint:locale==="bn"?"সার্ভারের অনুমোদন নেই":"Server authorization is absent",
  enabled:false,financialAuthorization:false,minTargetDp:48});
}
export function safeScreenFallback(locale:Locale):Readonly<{title:string;body:string;canPay:false}>{
 return Object.freeze({title:locale==="bn"?"ডেমো সেবা পাওয়া যাচ্ছে না":"Lab unavailable",
  body:locale==="bn"?"এই তথ্য দিয়ে লেনদেন করা যাবে না":"No payment can be made from this screen",
  canPay:false});
}
