/** Sample receipt and dispute screens: never imply an authorized or settled payment. */
import React,{useMemo,useState} from "react";
import {View,Text} from "react-native";
import type {AppSnapshot,Locale,SyntheticTransaction} from "../core/types.js";
import {t,operationLabel,localTime,statusLabel} from "../core/locales.js";
import {receiptFromTransaction,receiptProofWarning,serializeReceiptAsText} from "../core/receipts.js";
import {formatBDT} from "../core/money.js";
import {styles} from "./styles.js";
import {AppHeader,MobileScroll,LabBanner,WarningNote,ValueLine,SampleListRow,EmptyView,LabButton} from "./components.js";
export function SampleReceiptScreen({snapshot,locale,back}:{snapshot:AppSnapshot;locale:Locale;back:()=>void}){
 const [selected,setSelected]=useState<string|null>(null);
 const transaction=snapshot.transactions.find(x=>x.id===selected)??null;
 const receipt=useMemo(()=>transaction?receiptFromTransaction(transaction,{locale}):null,[transaction,locale]);
 return <><AppHeader title={t(locale,"requestReceipt")} back={back}/><MobileScroll>
  <LabBanner locale={locale}/>
  {!receipt?<View style={styles.card}><Text style={styles.cardTitle}>{t(locale,"activity")}</Text>
    {snapshot.transactions.map(tx=><SampleListRow key={tx.id} title={operationLabel(locale,tx.operation)}
      subtitle={`${localTime(locale,tx.occurredAt)} · ${statusLabel(locale,tx.state)}`}
      trailing={formatBDT(tx.amountPoisha,locale)} onPress={()=>setSelected(tx.id)}/>)}
    {snapshot.transactions.length===0?<EmptyView label={t(locale,"empty")}/>:null}
   </View>:<View style={styles.card}>
    <Text style={styles.cardTitle}>{receipt.title}</Text>
    <Text style={styles.tiny}>{localTime(locale,receipt.issuedAt)}</Text>
    {receipt.lines.map((line,index)=><ValueLine key={`${line.title}-${index}`} label={line.title} value={line.value} important={line.emphasis}/>)}
    <View style={styles.rule}/>
    <Text style={styles.tiny}>Display checksum (not a signature): {receipt.digest}</Text>
    <WarningNote message={receipt.disclaimer}/>
    <WarningNote message={receiptProofWarning(receipt).join(" · ")}/>
    <LabButton label={t(locale,"back")} variant="secondary" onPress={()=>setSelected(null)}/>
   </View>}
  <WarningNote message={t(locale,"receiptWarning")}/>
 </MobileScroll></>;
}
export function sampleReceiptNotBankProof():{paymentConfirmed:false;bankSettled:false;validReceiptFromProvider:false}{
 return {paymentConfirmed:false,bankSettled:false,validReceiptFromProvider:false};
}
