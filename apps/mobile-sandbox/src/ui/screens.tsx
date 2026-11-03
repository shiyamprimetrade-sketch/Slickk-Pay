/** Actual React Native sandbox screens. All financial controls are quote previews only. */
import React,{useMemo,useState} from "react";
import {View,Text,Pressable,Switch,Alert} from "react-native";
import type {AppSnapshot,Locale,Operation,Persona,Notification,SupportCase,PaymentDraft} from "../core/types.js";
import type {MobileLabController} from "../core/controller.js";
import {t,operationLabel,statusLabel,localTime} from "../core/locales.js";
import {formatBDT,parseBDT} from "../core/money.js";
import {homeModel,agentCell,activityCell,draftQuoteCard} from "../core/presenters.js";
import {activityPage} from "../core/activity.js";
import {maskPhone} from "../core/validation.js";
import {receiptFromTransaction,serializeReceiptAsText} from "../core/receipts.js";
import {merchantDirectory,estimateMerchantStatement} from "../core/merchants.js";
import {directoryAgents,agentDailyOperations} from "../core/agents.js";
import {buildDemoQR,parseDemoQR,qrPreviewLabel} from "../core/qr.js";
import {privacyAuditPreferences} from "../core/preferences.js";
import {DEFAULT_PREFERENCES} from "../core/preferences.js";
import {styles} from "./styles.js";
import {AppHeader,LabBanner,LabButton,ValueLine,WarningNote,LabTextInput,ChoiceChips,DemoTile,SampleListRow,MobileScroll,EmptyView,HiddenBalance} from "./components.js";
export interface ScreenProps {readonly snapshot:AppSnapshot;readonly locale:Locale;readonly controller:MobileLabController;readonly go:(name:string)=>void;readonly back:()=>void;readonly refresh:()=>void;}
export function HomeScreen({snapshot,locale,go}:ScreenProps){
 const model=homeModel(snapshot,locale);
 const items=[
  {name:"transfer_quote",label:t(locale,"transfer"),detail:t(locale,"previewOnly")},
  {name:"cash_in_quote",label:t(locale,"cashIn"),detail:t(locale,"serverRequired")},
  {name:"cash_quote",label:t(locale,"cashOut"),detail:t(locale,"serverRequired")},
  {name:"merchant_quote",label:t(locale,"merchantPay"),detail:t(locale,"feeWarning")},
  {name:"agents",label:t(locale,"findAgent"),detail:t(locale,"sampleAgents")},
  {name:"qr_preview",label:"QR",detail:t(locale,"notAQRPayment")},
  {name:"receipt",label:t(locale,"viewReceipt"),detail:t(locale,"receiptWarning")},
  {name:"support",label:t(locale,"support"),detail:t(locale,"sendDisabled")},
 ];
 return <>
 <AppHeader title={model.header.title} subtitle={model.header.subtitle}/>
 <MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"sampleBalance")}</Text>
   {model.cards.map(card=><View key={card.accountId} style={{gap:6}}>
    <ValueLine label={card.typeLabel} value={card.amount}/><Text style={styles.tiny}>{card.caveat}</Text>
   </View>)}
   {model.cards.length===0?<Text style={styles.tiny}>{t(locale,"none")}</Text>:null}
  </View>
  <Text style={styles.cardTitle}>{t(locale,"previewQuote")}</Text>
  <View style={styles.tileGrid}>{items.map(item=><DemoTile key={item.name} title={item.label} detail={item.detail} onPress={()=>go(item.name)}/>)}</View>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"recentActivity")}</Text>
   {model.activity.map(row=><SampleListRow key={row.id} title={row.title} subtitle={row.subtitle} trailing={row.trailing} onPress={()=>go("activity")}/>)}
   <LabButton label={t(locale,"more")} variant="secondary" onPress={()=>go("activity")}/>
  </View>
  <WarningNote message={t(locale,"noDeposits")}/>
 </MobileScroll>
 </>;
}
export function ActivityScreen({snapshot,locale,back}:ScreenProps){
 const [filter,setFilter]=useState<"all"|"completed"|"failed"|"review">("all");
 const [search,setSearch]=useState("");
 const results=activityPage(snapshot.transactions,snapshot.actor.id,{status:filter,search,pageSize:100});
 return <><AppHeader title={t(locale,"activity")} back={back}/><MobileScroll><LabBanner locale={locale} compact/>
  <ChoiceChips value={filter} onChange={setFilter} choices={[
   {value:"all",label:t(locale,"all")},{value:"completed",label:t(locale,"completed")},
   {value:"failed",label:t(locale,"failed")},{value:"review",label:t(locale,"reviewStatus")}]}/>
  <LabTextInput label={t(locale,"search")} value={search} onChange={setSearch} maxLength={80}/>
  <View style={styles.card}>
   {results.rows.map(tx=>{const cell=activityCell(tx,locale);return <SampleListRow key={cell.id} title={cell.title} subtitle={cell.subtitle} trailing={cell.trailing}/>;})}
   {results.total===0?<EmptyView label={t(locale,"empty")}/>:null}
  </View>
  <Text style={styles.tiny}>{results.total} {t(locale,"previewOnly")}</Text>
  <WarningNote message={t(locale,"staleWarning")}/>
 </MobileScroll></>;
}
export function AgentsScreen({snapshot,locale,back}:ScreenProps){
 const [search,setSearch]=useState("");
 const rows=directoryAgents(snapshot.agents,{search,limit:40});
 return <><AppHeader title={t(locale,"sampleAgents")} back={back}/><MobileScroll><LabBanner locale={locale} compact/>
   <LabTextInput label={t(locale,"search")} value={search} onChange={setSearch} maxLength={70}/>
   <View style={styles.card}>{rows.map(x=><SampleListRow key={x.id} title={x.name} subtitle={x.location}
    trailing={x.status==="sample_available"?t(locale,"previewOnly"):t(locale,"agentUnavailable")}/>)}
    {rows.length===0?<EmptyView label={t(locale,"empty")}/>:null}
   </View>
   <WarningNote message={t(locale,"callAgent")}/>
 </MobileScroll></>;
}
export function QuoteScreen({snapshot,locale,back,controller,refresh,operation}:{
 snapshot:AppSnapshot;locale:Locale;back:()=>void;controller:MobileLabController;refresh:()=>void;operation:Operation;
}){
 const [amount,setAmount]=useState("100.00"),[note,setNote]=useState("");
 const [current,setCurrent]=useState<PaymentDraft|null>(null),[error,setError]=useState<string|null>(null);
 const [consent,setConsent]=useState(false);
 const firstAgent=snapshot.agents.find(x=>x.acceptingRequests);
 const firstMerchant=snapshot.merchants.find(x=>x.active);
 const doQuote=()=>{
  try{
   const target={recipientId:operation==="transfer"?"sim_cust_0002":null,
    agentId:operation==="cash_in"||operation==="cash_out"?(firstAgent?.id??null):null,
    merchantId:operation==="merchant_payment"?(firstMerchant?.id??null):null};
   const draft=controller.newDraft({operation,amountText:amount,note,...target});
   const quoted=controller.quoteDraft(draft.id);
   setCurrent(quoted);setError(null);refresh();
  }catch(e){setError(e instanceof Error?e.message:"INVALID_QUOTE");setCurrent(null);}
 };
 const doReview=()=>{
  if(!current)return;
  try{
   const result=controller.reviewDraft(current.id,consent);
   setCurrent(result.draft);setError("No payment was sent. This is a reviewed local draft only.");refresh();
  }catch(e){setError(e instanceof Error?e.message:"REVIEW_FAILED");}
 };
 return <><AppHeader title={operationLabel(locale,operation)} back={back}/><MobileScroll><LabBanner locale={locale}/>
  <LabTextInput label={t(locale,"amount")} keyboardType="numeric" value={amount} onChange={value=>{
   setAmount(value);setCurrent(null);setError(null);}} maxLength={12}/>
  <LabTextInput label={t(locale,"notes")} value={note} onChange={setNote} maxLength={120}/>
  <LabButton label={t(locale,"prepare")} onPress={doQuote}/>
  {error?<WarningNote message={error}/>:null}
  {current?.quote? <View style={styles.card}>
   <Text style={styles.cardTitle}>{t(locale,"previewQuote")}</Text>
   <ValueLine label={t(locale,"principal")} value={formatBDT(current.quote.principalPoisha,locale)}/>
   <ValueLine label={t(locale,"fee")} value={formatBDT(current.quote.customerFeePoisha,locale)}/>
   <ValueLine label={t(locale,"tax")} value={t(locale,"unknown")}/>
   <View style={styles.rule}/>
   <ValueLine label={t(locale,"total")} value={formatBDT(current.quote.customerDebitPoisha,locale)} important/>
   <Text style={styles.tiny}>{t(locale,"rateNotice")}</Text>
   <View style={styles.row}><Text style={[styles.label,{flex:1}]}>{t(locale,"agreement")}</Text>
    <Switch accessibilityLabel={t(locale,"agreement")} value={consent} onValueChange={setConsent}/></View>
   <LabButton label={t(locale,"review")} onPress={doReview} disabled={!consent||current.state!=="quoted"}/>
   <WarningNote message={t(locale,"confirmNotAvailable")}/>
  </View>:null}
  <Text style={styles.tiny}>{t(locale,"serverRequired")}</Text>
 </MobileScroll></>;
}
export function NoticesScreen({snapshot,locale,back,controller,refresh}:ScreenProps){
 const items=controller.notices();
 return <><AppHeader title={t(locale,"notifications")} back={back}/><MobileScroll><LabBanner locale={locale} compact/>
  <View style={styles.card}>{items.map(item=><SampleListRow key={item.id}
   title={`${item.readAt===null?"● ":""}${item.title}`} subtitle={item.message}
   trailing={localTime(locale,item.createdAt)} onPress={()=>{controller.markNoticeRead(item.id,new Date().toISOString());refresh();}}/>)}
   {items.length===0?<EmptyView label={t(locale,"empty")}/>:null}
  </View>
 </MobileScroll></>;
}
export function SupportScreen({snapshot,locale,back,controller,refresh}:ScreenProps){
 const [subject,setSubject]=useState(""),[description,setDescription]=useState(""),[error,setError]=useState<string|null>(null);
 return <><AppHeader title={t(locale,"supportTitle")} back={back}/><MobileScroll><LabBanner locale={locale}/>
  <WarningNote message={t(locale,"sendDisabled")}/>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"createCase")}</Text>
   <LabTextInput label={t(locale,"subject")} value={subject} onChange={setSubject}/>
   <LabTextInput label={t(locale,"description")} value={description} onChange={setDescription} multiline maxLength={500}/>
   <LabButton label={t(locale,"prepare")} onPress={()=>{
    try{controller.prepareCase({subject,description,category:"technical"});setSubject("");setDescription("");setError(t(locale,"sendDisabled"));refresh();}
    catch(e){setError(e instanceof Error?e.message:"INVALID_CASE");}
   }}/>
   {error?<WarningNote message={error}/>:null}
  </View>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"recentActivity")}</Text>
   {snapshot.supportCases.map(c=><SampleListRow key={c.id} title={c.subject} subtitle={c.description} trailing={c.status}/>)}
   {controller.cases().map(c=><SampleListRow key={c.id} title={c.subject} subtitle={c.description} trailing={t(locale,"previewOnly")}/>)}
  </View>
 </MobileScroll></>;
}
export function SettingsScreen({snapshot,locale,controller,refresh,back}:ScreenProps){
 const preference=controller.state().preferences;
 return <><AppHeader title={t(locale,"settings")} back={back}/><MobileScroll><LabBanner locale={locale} compact/>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"language")}</Text>
   <ChoiceChips value={locale} choices={[{value:"bn",label:"বাংলা"},{value:"en",label:"English"}]}
    onChange={next=>{controller.dispatch({kind:"locale",locale:next});refresh();}}/>
   <Text style={styles.tiny}>{t(locale,"sampleOnly")}</Text>
  </View>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"profile")}</Text>
   <ValueLine label={t(locale,"customer")} value={snapshot.actor.name}/>
   <ValueLine label={t(locale,"phone")} value={maskPhone(snapshot.actor.phone)}/>
   <WarningNote message={t(locale,"sampleOnly")}/>
  </View>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"security")}</Text>
   <Text style={styles.body}>{t(locale,"neverSharePIN")}</Text>
   <LabButton label={t(locale,"lock")} variant="secondary" onPress={()=>{controller.dispatch({kind:"lock"});refresh();}}/>
  </View>
 </MobileScroll></>;
}
export function MerchantScreen({snapshot,locale,back}:ScreenProps){
 const entries=merchantDirectory(snapshot.merchants,"",false);
 const statement=estimateMerchantStatement(snapshot.transactions,snapshot.actor.id);
 return <><AppHeader title={t(locale,"merchantDashboard")} back={back}/><MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><ValueLine label={t(locale,"principal")} value={formatBDT(statement.grossPoisha,locale)}/>
   <ValueLine label={t(locale,"merchantFee")} value={formatBDT(statement.proposedFeesPoisha,locale)}/>
   <ValueLine label={t(locale,"total")} value={formatBDT(statement.netAfterFeesPoisha,locale)}/>
   <WarningNote message={t(locale,"noActualSettlement")}/>
  </View>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"merchant")}</Text>
   {entries.map(entry=><SampleListRow key={entry.id} title={entry.name} subtitle={entry.category} trailing={t(locale,"previewOnly")}/>)}
  </View>
 </MobileScroll></>;
}
export function AgentDashboardScreen({snapshot,locale,back}:ScreenProps){
 const agent=snapshot.agents.find(a=>a.actorId===snapshot.actor.id);
 const metrics=agentDailyOperations(snapshot.transactions);
 return <><AppHeader title={t(locale,"agentDashboard")} back={back}/><MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><Text style={styles.cardTitle}>{agent?.businessName??t(locale,"agent")}</Text>
   <ValueLine label={t(locale,"cashOnHand")} value={formatBDT(agent?.cashAvailablePoisha??0,locale)}/>
   <ValueLine label={t(locale,"cashIn")} value={formatBDT(metrics.inPoisha,locale)}/>
   <ValueLine label={t(locale,"cashOut")} value={formatBDT(metrics.outPoisha,locale)}/>
   <ValueLine label={t(locale,"reviewStatus")} value={String(metrics.issues)}/>
  </View><WarningNote message={t(locale,"serverRequired")}/>
 </MobileScroll></>;
}
export function QrScreen({snapshot,locale,back}:ScreenProps){
 const actor=snapshot.actor;
 const type=actor.role==="agent"?"agent":"merchant";
 const payload=buildDemoQR({kind:type,id:actor.id,label:actor.name,amountPoisha:null,reference:null});
 const result=parseDemoQR(payload);
 return <><AppHeader title="QR · LAB" back={back}/><MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><Text style={styles.cardTitle}>{result.ok?qrPreviewLabel(result.value,locale):t(locale,"unsupported")}</Text>
   <Text selectable style={styles.body}>{payload}</Text>
   <WarningNote message={t(locale,"notAQRPayment")}/>
  </View>
 </MobileScroll></>;
}
export function LimitationsScreen({locale,back}:ScreenProps){
 const warnings=[t(locale,"notReal"),t(locale,"noDeposits"),t(locale,"noLoans"),t(locale,"noActualSettlement"),t(locale,"neverSharePIN"),t(locale,"feeWarning")];
 return <><AppHeader title={t(locale,"unsupported")} back={back}/><MobileScroll><LabBanner locale={locale}/>
  {warnings.map((message,i)=><WarningNote key={i} message={message}/>)}
 </MobileScroll></>;
}
