/** UI view models are immutable and always include truthful demo captions. */
import type {AppSnapshot,Account,Locale,PaymentDraft,SyntheticTransaction,AgentProfile,MoneyQuote,Persona} from "./types.js";
import {formatBDT} from "./money.js";
import {t,operationLabel,localTime,statusLabel} from "./locales.js";
import {maskPhone,safeDisplayLabel} from "./validation.js";
import {activityRowModel} from "./activity.js";
import {dashboardForSnapshot,dashboardLabels} from "./analytics.js";
export interface HeaderModel {readonly title:string;readonly subtitle:string;readonly avatarLetters:string;readonly locale:Locale;readonly warning:string;}
export interface BalanceCard {readonly accountId:string;readonly amount:string;readonly typeLabel:string;readonly caveat:string;readonly disabled:boolean;}
export interface ListCell {readonly id:string;readonly title:string;readonly subtitle:string;readonly trailing:string;readonly accessibilityLabel:string;readonly pressable:boolean;}
export interface QuoteCard {readonly amount:string;readonly fee:string;readonly tax:string;readonly total:string;readonly commission:string;readonly status:string;readonly disclaimers:readonly string[];}
export interface HomeModel {readonly header:HeaderModel;readonly cards:readonly BalanceCard[];readonly activity:readonly ListCell[];readonly metrics:readonly {label:string;value:string;caveat:string}[];readonly simulation:true;}
export function headerModel(snapshot:AppSnapshot,locale:Locale):HeaderModel{
 const name=safeDisplayLabel(snapshot.actor.name),words=name.split(" ").filter(Boolean);
 const avatarLetters=(words[0]?.[0]??"D")+(words.length>1?words[1]?.[0]??"":"");
 return Object.freeze({title:name,subtitle:maskPhone(snapshot.actor.phone),avatarLetters:avatarLetters.toUpperCase(),
  locale,warning:t(locale,"simulationBanner")});
}
export function balanceCard(account:Account,locale:Locale):BalanceCard{
 const labels:Record<Account["kind"],string>={customer:t(locale,"sampleBalance"),agent_float:t(locale,"availableFloat"),
  agent_commission:t(locale,"commission"),merchant:t(locale,"sampleBalance")};
 return Object.freeze({accountId:account.id,amount:formatBDT(account.poisha,locale),
  typeLabel:labels[account.kind],caveat:t(locale,"noDeposits"),disabled:account.frozen});
}
export function activityCell(tx:SyntheticTransaction,locale:Locale):ListCell{
 const row=activityRowModel(tx,locale);
 return Object.freeze({id:tx.id,title:row.heading,subtitle:row.subheading,
  trailing:`${row.amount} · ${row.status}`,
  accessibilityLabel:`${row.heading}, ${row.amount}, ${row.status}, demonstration only`,pressable:true});
}
export function agentCell(agent:AgentProfile,locale:Locale):ListCell{
 return Object.freeze({id:agent.id,title:safeDisplayLabel(agent.businessName),subtitle:safeDisplayLabel(agent.locationLabel),
  trailing:agent.acceptingRequests?formatBDT(agent.cashAvailablePoisha,locale):t(locale,"agentUnavailable"),
  accessibilityLabel:`${agent.businessName}, sample agent, ${agent.locationLabel}, no payment available`,pressable:true});
}
export function draftQuoteCard(draft:PaymentDraft,locale:Locale):QuoteCard{
 if(!draft.quote)throw new Error("QUOTE_REQUIRED");
 const q=draft.quote;
 return Object.freeze({amount:formatBDT(q.principalPoisha,locale),fee:formatBDT(q.customerFeePoisha,locale),
  tax:t(locale,"unknown"),total:formatBDT(q.customerDebitPoisha,locale),
  commission:formatBDT(q.agentCommissionPoisha,locale),status:draft.state,
  disclaimers:Object.freeze([t(locale,"rateNotice"),t(locale,"serverRequired"),t(locale,"noLiveTransfer")])});
}
export function quoteCardDirect(quote:MoneyQuote,locale:Locale):QuoteCard{
 return Object.freeze({amount:formatBDT(quote.principalPoisha,locale),fee:formatBDT(quote.customerFeePoisha,locale),
  tax:t(locale,"unknown"),total:formatBDT(quote.customerDebitPoisha,locale),
  commission:formatBDT(quote.agentCommissionPoisha,locale),status:t(locale,"previewOnly"),
  disclaimers:Object.freeze([t(locale,"feeWarning"),t(locale,"receiptWarning")])});
}
export function homeModel(snapshot:AppSnapshot,locale:Locale):HomeModel{
 const dashboard=dashboardForSnapshot(snapshot);
 return Object.freeze({header:headerModel(snapshot,locale),cards:Object.freeze(snapshot.accounts.map(x=>balanceCard(x,locale))),
  activity:Object.freeze(snapshot.transactions.slice(0,4).map(x=>activityCell(x,locale))),
  metrics:dashboardLabels(dashboard,locale),simulation:true});
}
export function notificationCountLabel(count:number,locale:Locale):string{
 return locale==="bn"?`নমুনা বিজ্ঞপ্তি: ${count}`:`${count} sample notices`;
}
export function agentCashBanner(agent:AgentProfile,locale:Locale):string{
 return `${agent.businessName} · ${formatBDT(agent.cashAvailablePoisha,locale)} · ${t(locale,"previewOnly")}`;
}
export function transactionDetailRows(tx:SyntheticTransaction,locale:Locale):readonly {label:string;value:string}[]{
 return Object.freeze([
  {label:t(locale,"ref"),value:tx.reference},
  {label:t(locale,"status"),value:statusLabel(locale,tx.state)},
  {label:t(locale,"principal"),value:formatBDT(tx.amountPoisha,locale)},
  {label:t(locale,"fee"),value:formatBDT(tx.feePoisha,locale)},
  {label:t(locale,"date"),value:localTime(locale,tx.occurredAt)},
  {label:t(locale,"notReal"),value:t(locale,"receiptWarning")},
 ]);
}
export function emptyListModel(locale:Locale):{title:string;description:string}{
 return {title:t(locale,"empty"),description:t(locale,"notReal")};
}
export function personaShortLabel(persona:Persona,locale:Locale):string{
 return persona==="agent"?t(locale,"agent"):persona==="merchant"?t(locale,"merchant"):t(locale,"customer");
}
export function readOnlyBanner(locale:Locale):{title:string;body:string;critical:true}{
 return {title:t(locale,"simulationBanner"),body:t(locale,"noLiveTransfer"),critical:true};
}
