/** Two-party cash handover tabletop demonstration. Never confirms real cash transfer. */
import React,{useMemo,useState} from "react";
import {View,Text,Switch} from "react-native";
import type {AppSnapshot,Locale} from "../core/types.js";
import {t} from "../core/locales.js";
import {formatBDT,parseBDT} from "../core/money.js";
import {newHandoverPreview,quoteHandover,cancelHandoverPreview,handoverAuditTrail,type HandoverPreview} from "../core/agentflow.js";
import {styles} from "./styles.js";
import {AppHeader,LabBanner,LabButton,ValueLine,WarningNote,MobileScroll,LabTextInput,ChoiceChips} from "./components.js";
export function AgentCashSandboxScreen({snapshot,locale,back}:{snapshot:AppSnapshot;locale:Locale;back:()=>void}){
 const [kind,setKind]=useState<"cash_in"|"cash_out">("cash_out");
 const [amountText,setAmount]=useState("1000.00");
 const [item,setItem]=useState<HandoverPreview|null>(null);
 const [error,setError]=useState<string|null>(null);

 const agent=useMemo(()=>snapshot.agents.find(x=>x.acceptingRequests),[snapshot.agents]);
 const build=()=>{
  try{
   if(!agent)throw new Error("NO_SAMPLE_AGENT");
   const principal=parseBDT(amountText);
   const start=newHandoverPreview(snapshot.actor.id,agent,kind,principal,new Date().toISOString());
   const quoted=quoteHandover(start,new Date().toISOString());
   setItem(quoted);setError(null);
  }catch(e){setError(e instanceof Error?e.message:"INVALID_SAMPLE_CASH_REQUEST");setItem(null);}
 };
 const cancel=()=>{if(item)setItem(cancelHandoverPreview(item,new Date().toISOString()));};
 return <><AppHeader title={t(locale,"cashOut")} subtitle={t(locale,"previewOnly")} back={back}/>
 <MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"selectAgent")}</Text>
   <Text style={styles.body}>{agent?.businessName??t(locale,"agentUnavailable")}</Text>
   <ChoiceChips value={kind} onChange={value=>{setKind(value);setItem(null);}} choices={[
    {value:"cash_in",label:t(locale,"cashIn")},{value:"cash_out",label:t(locale,"cashOut")}]}/>
   <LabTextInput label={t(locale,"amount")} value={amountText} onChange={setAmount} keyboardType="numeric"/>
   <LabButton label={t(locale,"previewQuote")} onPress={build}/>
  </View>
  {item?<View style={styles.card}>
   <Text style={styles.cardTitle}>{t(locale,"previewOnly")} · {item.step}</Text>
   <ValueLine label={t(locale,"principal")} value={formatBDT(item.amountPoisha,locale)}/>
   <ValueLine label={t(locale,"fee")} value={formatBDT(item.quote?.customerFeePoisha??0,locale)}/>
   <ValueLine label={t(locale,"commissionEarned")} value={formatBDT(item.quote?.agentCommissionPoisha??0,locale)}/>
   <Text style={styles.tiny}>{t(locale,"rateNotice")}</Text>
   {item.step==="quoted"?<WarningNote message="Both customer and agent authentication, and physical handover verification, require a future independently authenticated server. This local agent cannot approve either side."/>:null}
   {item.step==="quoted"?<LabButton label={t(locale,"cancel")} variant="secondary" onPress={cancel}/>:null}
   {handoverAuditTrail(item).map(check=><ValueLine key={check.check} label={check.check} value={check.passed?"DEMO ✓":"NOT VERIFIED"}/>)}
  </View>:null}
  {error?<WarningNote message={error}/>:null}
  <WarningNote message={t(locale,"neverSharePIN")}/>
  <WarningNote message={t(locale,"confirmNotAvailable")}/>
 </MobileScroll></>;
}
