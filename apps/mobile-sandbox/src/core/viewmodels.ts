/** Accessible, low-bandwidth screen-model builders for Android-first layouts. */
import type {Locale,AppSnapshot,PaymentDraft,Notification,SupportCase,MoneyQuote,Persona} from "./types.js";
import type {MobileState} from "./controller.js";
import {homeModel,agentCell,activityCell,quoteCardDirect} from "./presenters.js";
import {formatBDT} from "./money.js";
import {t} from "./locales.js";
import {selectNotices} from "./notifications.js";
import {supportCaseSummary} from "./support.js";
export type IconName="home"|"history"|"users"|"shield"|"settings"|"support"|"qr"|"cash"|"bell"|"merchant";
export interface ActionTile {readonly id:string;readonly title:string;readonly icon:IconName;readonly explanation:string;readonly interactive:boolean;readonly financialPosting:false;}
export interface MobilePageModel {readonly title:string;readonly subtitle:string;readonly banner:string;readonly tiles:readonly ActionTile[];readonly accountTotal:string;readonly safetyWarnings:readonly string[];}
function actionTile(id:string,title:string,icon:IconName,explanation:string,interactive=true):ActionTile{
 return Object.freeze({id,title,icon,explanation,interactive,financialPosting:false});
}
export function customerActionTiles(locale:Locale):readonly ActionTile[]{
 return Object.freeze([
  actionTile("transfer",t(locale,"transfer"),"cash",t(locale,"previewOnly")),
  actionTile("cash_in",t(locale,"cashIn"),"cash",t(locale,"serverRequired")),
  actionTile("cash_out",t(locale,"cashOut"),"cash",t(locale,"serverRequired")),
  actionTile("merchant",t(locale,"merchantPay"),"merchant",t(locale,"previewOnly")),
  actionTile("agents",t(locale,"findAgent"),"users",t(locale,"sampleAgents")),
  actionTile("support",t(locale,"support"),"support",t(locale,"sendDisabled")),
 ]);
}
export function agentActionTiles(locale:Locale):readonly ActionTile[]{
 return Object.freeze([
  actionTile("agent_directory",t(locale,"sampleAgents"),"users",t(locale,"sampleOnly")),
  actionTile("cash_quote",t(locale,"previewQuote"),"cash",t(locale,"feeWarning")),
  actionTile("activity",t(locale,"recentActivity"),"history",t(locale,"staleWarning")),
  actionTile("qr",t(locale,"notAQRPayment"),"qr",t(locale,"previewOnly")),
  actionTile("support",t(locale,"support"),"support",t(locale,"sendDisabled")),
 ]);
}
export function merchantActionTiles(locale:Locale):readonly ActionTile[]{
 return Object.freeze([
  actionTile("merchant_quote",t(locale,"merchantPay"),"merchant",t(locale,"feeWarning")),
  actionTile("activity",t(locale,"statement"),"history",t(locale,"noActualSettlement")),
  actionTile("qr",t(locale,"notAQRPayment"),"qr",t(locale,"previewOnly")),
  actionTile("support",t(locale,"support"),"support",t(locale,"sendDisabled")),
 ]);
}
export function screenModel(state:MobileState):MobilePageModel{
 const locale=state.preferences.locale,persona=state.snapshot.actor.role;
 const tiles=persona==="customer"?customerActionTiles(locale):persona==="agent"?agentActionTiles(locale):merchantActionTiles(locale);
 const summary=homeModel(state.snapshot,locale);
 const balance=state.preferences.showFictionalAmounts?summary.cards.map(x=>x.amount).join(" · "):"••••";
 return Object.freeze({title:summary.header.title,subtitle:summary.header.subtitle,
  banner:t(locale,"simulationBanner"),tiles,accountTotal:balance,
  safetyWarnings:Object.freeze([t(locale,"noDeposits"),t(locale,"noLiveTransfer")])});
}
export function agentsView(snapshot:AppSnapshot,locale:Locale):{title:string;rows:readonly ReturnType<typeof agentCell>[];footer:string}{
 return {title:t(locale,"sampleAgents"),rows:Object.freeze(snapshot.agents.map(x=>agentCell(x,locale))),
  footer:t(locale,"callAgent")};
}
export function activityView(snapshot:AppSnapshot,locale:Locale):{title:string;rows:readonly ReturnType<typeof activityCell>[];warning:string}{
 return {title:t(locale,"activity"),rows:Object.freeze(snapshot.transactions.map(x=>activityCell(x,locale))),
  warning:t(locale,"staleWarning")};
}
export function noticesView(snapshot:AppSnapshot,locale:Locale):{rows:readonly {id:string;title:string;message:string;unread:boolean}[];title:string}{
 const notices=selectNotices(snapshot.notices,snapshot.actor.id);
 return {title:t(locale,"notifications"),rows:Object.freeze(notices.map(n=>({id:n.id,title:n.title,message:n.message,unread:n.readAt===null})))};
}
export function supportView(cases:readonly SupportCase[],locale:Locale):{rows:readonly {id:string;label:string}[];warning:string}{
 return {rows:Object.freeze(cases.map(c=>({id:c.id,label:supportCaseSummary(c,locale)}))),warning:t(locale,"sendDisabled")};
}
export function quoteView(quote:MoneyQuote,locale:Locale):{rows:readonly {label:string;value:string}[];warnings:readonly string[]}{
 const model=quoteCardDirect(quote,locale);
 return {rows:Object.freeze([
  {label:t(locale,"principal"),value:model.amount},
  {label:t(locale,"fee"),value:model.fee},
  {label:t(locale,"tax"),value:model.tax},
  {label:t(locale,"total"),value:model.total},
 ]),warnings:model.disclaimers};
}
export function draftView(draft:PaymentDraft,locale:Locale):{summary:string;state:string;amount:string;serverPosted:false}{
 return {summary:operationTitle(draft.operation,locale),state:draft.state,
  amount:formatBDT(draft.principalPoisha,locale),serverPosted:false};
}
function operationTitle(operation:PaymentDraft["operation"],locale:Locale):string{
 const names:Record<PaymentDraft["operation"],string>={transfer:t(locale,"transfer"),cash_in:t(locale,"cashIn"),cash_out:t(locale,"cashOut"),
  merchant_payment:t(locale,"merchantPay"),balance_inquiry:t(locale,"balanceInquiry")};
 return names[operation];
}
export function menuAccess(persona:Persona):readonly {name:string;allowed:boolean}[]{
 return Object.freeze([
  {name:"customer",allowed:persona==="customer"},
  {name:"agent",allowed:persona==="agent"},
  {name:"merchant",allowed:persona==="merchant"},
  {name:"settings",allowed:true},
  {name:"support",allowed:true},
 ]);
}
export function mobileScreenAccessibilityWarning(locale:Locale):string{
 return `${t(locale,"simulationBanner")}. ${t(locale,"receiptWarning")}`;
}
export function headingForNotice(notice:Notification,locale:Locale):string{
 return `${t(locale,"notifications")}: ${notice.title}`;
}
