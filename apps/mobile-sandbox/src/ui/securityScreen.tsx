/** Self-contained privacy and security education; no live identity enrollment or PIN storage. */
import React,{useMemo,useState} from "react";
import {View,Text,Switch} from "react-native";
import type {AppSnapshot,Locale} from "../core/types.js";
import {t} from "../core/locales.js";
import {maskPhone} from "../core/validation.js";
import {sampleDataAttestation,redactLogRecord} from "../core/privacy.js";
import {securityChecklist,startDemoSession,safeStoragePolicy} from "../core/security.js";
import {auditMobileSnapshot,releaseGates,auditDisclaimer} from "../core/audit.js";
import {accessibleBalancePrivacy} from "../core/accessibility.js";
import {styles} from "./styles.js";
import {AppHeader,MobileScroll,LabBanner,LabButton,WarningNote,ValueLine} from "./components.js";
export function LabSecurityScreen({snapshot,locale,back,onLock}:{snapshot:AppSnapshot;locale:Locale;back:()=>void;onLock:()=>void}){
 const [hidden,setHidden]=useState(true);
 const report=useMemo(()=>auditMobileSnapshot(snapshot),[snapshot]);
 const policy=securityChecklist({appForeground:true,screenProtected:false,hasTrustedLocalClock:false,network:"offline",securityNoticeAcknowledged:true},
   startDemoSession(snapshot.actor.role,snapshot.actor.id,Date.now()),Date.now());
 return <><AppHeader title={t(locale,"security")} back={back}/><MobileScroll>
  <LabBanner locale={locale}/>
  <View style={styles.card}>
   <Text style={styles.cardTitle}>{t(locale,"profile")}</Text>
   <ValueLine label="Name" value={snapshot.actor.name}/>
   <ValueLine label={t(locale,"phone")} value={maskPhone(snapshot.actor.phone)}/>
   <WarningNote message={t(locale,"sampleOnly")}/>
  </View>
  <View style={styles.card}>
   <Text style={styles.cardTitle}>{t(locale,"privacy")}</Text>
   <Text style={styles.body}>{sampleDataAttestation(snapshot)}</Text>
   <View style={styles.row}><Text style={[styles.label,{flex:1}]}>{accessibleBalancePrivacy(hidden,locale)}</Text>
    <Switch value={!hidden} onValueChange={on=>setHidden(!on)} accessibilityLabel="Toggle sample balance visibility"/></View>
   <Text style={styles.tiny}>{t(locale,"noDeposits")}</Text>
  </View>
  <View style={styles.card}>
   <Text style={styles.cardTitle}>{t(locale,"auditTrail")}</Text>
   <ValueLine label="Local fixture validation" value={report.verifiedLocalFixtures?"PASS":"REVIEW"}/>
   <ValueLine label="Independent security review" value="NOT PERFORMED"/>
   {policy.map(p=><ValueLine key={p.name} label={p.name} value={p.passed?"Local ✓":"UNVERIFIED"}/>)}
   <Text style={styles.tiny}>{auditDisclaimer(locale)}</Text>
  </View>
  <View style={styles.card}>
   <Text style={styles.cardTitle}>Live financial release gates</Text>
   {releaseGates().map(g=><ValueLine key={g.code} label={g.code} value="NOT VERIFIED"/>)}
   <WarningNote message={t(locale,"neverSharePIN")}/>
   <LabButton label={t(locale,"lock")} onPress={onLock}/>
  </View>
 </MobileScroll></>;
}
