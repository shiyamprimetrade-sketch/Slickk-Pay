/** In-app demo notifications. No SMS or push delivery credentials are present. */
import type {Notification,ActorId,NoticeCategory,Severity,Locale} from "./types.js";
import {safeTransactionDescription} from "./privacy.js";
export interface NoticeFilter {readonly unreadOnly?:boolean;readonly category?:NoticeCategory|"all";readonly severity?:Severity|"all";readonly max?:number;}
export interface NoticeSummary {readonly count:number;readonly unread:number;readonly critical:number;readonly latestAt:string|null;}
export function selectNotices(all:readonly Notification[],owner:ActorId,filter:NoticeFilter={}):readonly Notification[]{
 const max=filter.max??100;
 if(!Number.isSafeInteger(max)||max<1||max>500)throw new Error("INVALID_NOTICE_LIMIT");
 return Object.freeze(all.filter(n=>n.actorId===owner&&n.simulation===true)
  .filter(n=>!filter.unreadOnly||n.readAt===null)
  .filter(n=>!filter.category||filter.category==="all"||n.category===filter.category)
  .filter(n=>!filter.severity||filter.severity==="all"||n.severity===filter.severity)
  .sort((a,b)=>b.createdAt.localeCompare(a.createdAt)).slice(0,max));
}
export function noticeSummary(all:readonly Notification[],owner:ActorId):NoticeSummary{
 const filtered=selectNotices(all,owner);
 return Object.freeze({count:filtered.length,unread:filtered.filter(x=>x.readAt===null).length,
  critical:filtered.filter(x=>x.severity==="critical").length,
  latestAt:filtered[0]?.createdAt??null});
}
export function localMarkRead(notice:Notification,at:string):Notification{
 if(notice.readAt!==null)return notice;
 if(!Number.isFinite(Date.parse(at))||at<notice.createdAt)throw new Error("INVALID_NOTICE_TIME");
 return Object.freeze({...notice,readAt:at});
}
export function localMarkAllRead(all:readonly Notification[],owner:ActorId,at:string):readonly Notification[]{
 return Object.freeze(all.map(n=>n.actorId===owner&&n.readAt===null?localMarkRead(n,at):n));
}
export function noticeDisplay(notice:Notification,locale:Locale):{title:string;message:string;badge:string;read:boolean}{
 if(notice.simulation!==true)throw new Error("UNVERIFIED_NOTICE");
 return {title:safeTransactionDescription(notice.title),message:safeTransactionDescription(notice.message),
  badge:locale==="bn"?"নমুনা বিজ্ঞপ্তি":"Sample notice",read:notice.readAt!==null};
}
export function allowedNoticeLink(notice:Notification):string|null{
 if(!notice.simulation||!notice.deepLink)return null;
 try{
  const target=new URL(notice.deepLink);
  if(target.protocol!=="slickkpaylab:"||target.username||target.password||target.hash)return null;
  if(["cash_quote","transfer_quote","merchant_quote"].includes(target.hostname))return null;
  return notice.deepLink;
 }catch{return null;}
}
export function groupNoticesByCategory(all:readonly Notification[]):Readonly<Record<NoticeCategory,number>>{
 const grouped:Record<NoticeCategory,number>={account:0,security:0,cash:0,merchant:0,system:0};
 for(const notice of all){if(!notice.simulation)throw new Error("UNSAFE_NOTICE");grouped[notice.category]++;}
 return Object.freeze(grouped);
}
export function securityNoticePriority(all:readonly Notification[]):readonly Notification[]{
 return Object.freeze([...all].sort((a,b)=>{
  const priority=(value:Severity)=>value==="critical"?3:value==="warning"?2:1;
  return priority(b.severity)-priority(a.severity)||b.createdAt.localeCompare(a.createdAt);
 }));
}
export function makeLocalNotice(actorId:ActorId,title:string,message:string,at:string,severity:Severity="info"):Notification{
 if(!actorId.startsWith("sim_")||title.length>100||message.length>200)throw new Error("INVALID_LOCAL_NOTICE");
 if(!Number.isFinite(Date.parse(at)))throw new Error("INVALID_NOTICE_TIMESTAMP");
 return Object.freeze({simulation:true,dataProvenance:"fixture",id:`sim_notice_local_${at.replace(/\D/g,"")}`,
  actorId,category:"system",severity,title:safeTransactionDescription(title),message:safeTransactionDescription(message),
  createdAt:at,readAt:null,deepLink:null});
}
export function noticePrivacyChecklist(notice:Notification):readonly {code:string;passed:boolean}[]{
 return Object.freeze([
  {code:"SIMULATED",passed:notice.simulation===true},
  {code:"NO_PHONE",passed:!/(?:\+?8801[3-9]\d{8})/.test(notice.message)},
  {code:"NO_CREDENTIAL",passed:!/(?:password|pin|otp)\s*[:=]/i.test(notice.message)},
  {code:"APP_SCHEME_ONLY",passed:notice.deepLink===null||allowedNoticeLink(notice)!==null},
 ]);
}
export function unreadBadge(all:readonly Notification[],owner:ActorId):string|null{
 const count=noticeSummary(all,owner).unread;
 return count?count>99?"99+":String(count):null;
}
export function deduplicateNotices(all:readonly Notification[]):readonly Notification[]{
 const seen=new Set<string>();
 return Object.freeze(all.filter(n=>{if(seen.has(n.id))return false;seen.add(n.id);return true;}));
}
