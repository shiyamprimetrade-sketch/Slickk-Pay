/** Slickk Pay LAB: standalone Android-first Expo app, deliberately no real payment API. */
import React,{useEffect,useMemo,useState} from "react";
import {SafeAreaView,StatusBar,View,Text,Pressable,BackHandler} from "react-native";
import type {Persona} from "./src/core/types.js";
import {MobileLabController,type MobileState} from "./src/core/controller.js";
import {t,roleLabel} from "./src/core/locales.js";
import {visibleTabs,type ScreenName} from "./src/core/navigation.js";
import {AppHeader,LabBanner,LabButton,MobileScroll,ChoiceChips,BottomTabs,WarningNote,NetworkHint} from "./src/ui/components.js";
import {styles,palette} from "./src/ui/styles.js";
import {SampleReceiptScreen} from "./src/ui/receiptScreen.js";
import {LabSecurityScreen} from "./src/ui/securityScreen.js";
import {MerchantToolsScreen} from "./src/ui/merchantToolsScreen.js";
import {AgentCashSandboxScreen} from "./src/ui/agentCashScreen.js";
import {HomeScreen,ActivityScreen,AgentsScreen,QuoteScreen,NoticesScreen,SupportScreen,SettingsScreen,MerchantScreen,AgentDashboardScreen,QrScreen,LimitationsScreen} from "./src/ui/screens.js";
const controller=new MobileLabController();
const recognized=new Set<ScreenName>(["home","activity","agents","agent_detail","cash_quote","cash_in_quote","transfer_quote","merchant_quote","receipt",
 "security","settings","support","agent_dashboard","merchant_dashboard","notifications","qr_preview","privacy","limitations"]);
function allowedScreen(value:string):ScreenName{return recognized.has(value as ScreenName)?value as ScreenName:"limitations";}
export default function App(){
 const [state,setState]=useState<MobileState>(()=>controller.state());
 const [onboarded,setOnboarded]=useState(false);
 const [consent,setConsent]=useState(false);
 useEffect(()=>controller.subscribe(setState),[]);
 useEffect(()=>{
  const handler=BackHandler.addEventListener("hardwareBackPress",()=>{
   if(state.locked||!onboarded)return false;
   controller.dispatch({kind:"back"});return true;
  });
  return ()=>handler.remove();
 },[state.locked,onboarded]);
 const locale=state.preferences.locale;
 const persona=state.snapshot.actor.role;
 const screen=state.screen;
 const go=(raw:string)=>{
  try{controller.dispatch({kind:"navigate",screen:allowedScreen(raw)});}
  catch{controller.dispatch({kind:"navigate",screen:"limitations"});}
 };
 const back=()=>{controller.dispatch({kind:"back"});};
 const refresh=()=>setState(controller.state());
 const shared={snapshot:state.snapshot,locale,controller,go,back,refresh};
 const tabs=visibleTabs(persona).map(name=>({name,title:name==="home"?t(locale,"home"):
  name==="agent_dashboard"?t(locale,"agent"):name==="merchant_dashboard"?t(locale,"merchant"):
  name==="activity"?t(locale,"activity"):name==="agents"?t(locale,"agents"):
  name==="notifications"?t(locale,"notifications"):name==="support"?t(locale,"support"):
  t(locale,"settings")}));
 if(!onboarded){
  return <SafeAreaView style={styles.safe}><StatusBar barStyle="dark-content" backgroundColor={palette.paper}/>
   <AppHeader title={t(locale,"appName")} subtitle={t(locale,"loginSample")}/>
   <MobileScroll><LabBanner locale={locale}/>
    <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"profile")}</Text>
     <ChoiceChips value={persona} onChange={(next:Persona)=>controller.dispatch({kind:"persona",persona:next})}
      choices={[{value:"customer",label:t(locale,"customer")},{value:"agent",label:t(locale,"agent")},
       {value:"merchant",label:t(locale,"merchant")}]}/>
     <Text style={styles.body}>{state.snapshot.actor.name}</Text>
     <Text style={styles.tiny}>{t(locale,"sampleOnly")}</Text>
    </View>
    <View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"language")}</Text>
      <ChoiceChips value={locale} onChange={next=>controller.dispatch({kind:"locale",locale:next})}
       choices={[{value:"bn",label:"বাংলা"},{value:"en",label:"English"}]}/>
    </View>
    <View style={styles.card}><Text style={styles.body}>{t(locale,"notReal")}</Text>
     <View style={styles.row}><Text style={[styles.label,{flex:1}]}>{t(locale,"agreement")}</Text>
      <Pressable accessibilityRole="checkbox" accessibilityState={{checked:consent}} onPress={()=>setConsent(!consent)}
       style={styles.chip}><Text style={styles.chipText}>{consent?"☑":"☐"}</Text></Pressable></View>
     <LabButton label={t(locale,"signIn")} disabled={!consent} onPress={()=>setOnboarded(true)}/>
    </View>
   </MobileScroll>
  </SafeAreaView>;
 }
 if(state.locked){
  return <SafeAreaView style={styles.safe}><StatusBar barStyle="dark-content" backgroundColor={palette.paper}/>
   <AppHeader title={t(locale,"signedOut")}/><MobileScroll><LabBanner locale={locale}/>
    <WarningNote message={t(locale,"noAuthority")}/>
    <LabButton label={t(locale,"unlock")} onPress={()=>controller.unlock(Date.now(),true)}/>
    <LabButton label={t(locale,"back")} variant="secondary" onPress={()=>{setOnboarded(false);setConsent(false);}}/>
   </MobileScroll>
  </SafeAreaView>;
 }
 let content:React.ReactNode;
 if(screen==="home")content=<HomeScreen {...shared}/>;
 else if(screen==="activity")content=<ActivityScreen {...shared}/>;
 else if(screen==="agents"||screen==="agent_detail")content=<AgentsScreen {...shared}/>;
 else if(screen==="transfer_quote")content=<QuoteScreen {...shared} operation="transfer"/>;
 else if(screen==="cash_quote")content=<QuoteScreen {...shared} operation="cash_out"/>;
 else if(screen==="cash_in_quote")content=<QuoteScreen {...shared} operation="cash_in"/>;
 else if(screen==="merchant_quote")content=<QuoteScreen {...shared} operation="merchant_payment"/>;
 else if(screen==="notifications")content=<NoticesScreen {...shared}/>;
 else if(screen==="support")content=<SupportScreen {...shared}/>;
 else if(screen==="security"||screen==="privacy")content=<LabSecurityScreen snapshot={state.snapshot} locale={locale} back={back} onLock={()=>controller.dispatch({kind:"lock"})}/>;
 else if(screen==="settings")content=<SettingsScreen {...shared}/>;
 else if(screen==="receipt")content=<SampleReceiptScreen snapshot={state.snapshot} locale={locale} back={back}/>;
 else if(screen==="cash_in_quote"&&persona==="agent")content=<AgentCashSandboxScreen snapshot={state.snapshot} locale={locale} back={back}/>;
 else if(screen==="agent_dashboard")content=<AgentDashboardScreen {...shared}/>;
 else if(screen==="merchant_dashboard")content=<MerchantScreen {...shared}/>;
 else if(screen==="qr_preview")content=<QrScreen {...shared}/>;
 else content=<LimitationsScreen {...shared}/>;
 return <SafeAreaView style={styles.safe}>
  <StatusBar barStyle="dark-content" backgroundColor={palette.paper}/>
  <View style={{flex:1}}>{content}</View>
  <View style={{paddingHorizontal:12,paddingVertical:3,backgroundColor:palette.white}}>
   <NetworkHint network={state.network} locale={locale}/></View>
  <BottomTabs tabs={tabs} current={screen} onSelect={raw=>{
   const selected=allowedScreen(raw);
   try{controller.dispatch({kind:"navigate",screen:selected});}catch{controller.dispatch({kind:"back"});}
  }}/>
 </SafeAreaView>;
}
