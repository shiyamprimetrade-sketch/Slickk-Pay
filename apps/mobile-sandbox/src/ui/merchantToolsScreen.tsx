/** Merchant-facing simulated business tools; no real payment link or settlement created. */
import React,{useMemo,useState} from "react";
import {Text,View} from "react-native";
import type {AppSnapshot,Locale} from "../core/types.js";
import {t} from "../core/locales.js";
import {parseBDT,formatBDT} from "../core/money.js";
import {merchantInvoice,invoiceToDescription,merchantCapabilities} from "../core/merchants.js";
import {styles} from "./styles.js";
import {AppHeader,MobileScroll,LabBanner,LabTextInput,LabButton,ValueLine,WarningNote,SampleListRow} from "./components.js";
export function MerchantToolsScreen({snapshot,locale,back}:{snapshot:AppSnapshot;locale:Locale;back:()=>void}){
 const [description,setDescription]=useState("Sample grocery order"),[unit,setUnit]=useState("250.00");
 const [quantity,setQuantity]=useState("1"),[invoice,setInvoice]=useState<ReturnType<typeof merchantInvoice>|null>(null);
 const [error,setError]=useState<string|null>(null);
 const profile=snapshot.merchants.find(x=>x.id===snapshot.actor.id);
 const capabilities=useMemo(()=>merchantCapabilities(),[]);
 const prepare=()=>{
  try{
   if(!profile)throw new Error("SAMPLE_MERCHANT_REQUIRED");
   const parsedQuantity=Number(quantity);
   const result=merchantInvoice(profile.id,description,parsedQuantity,parseBDT(unit),new Date().toISOString());
   setInvoice(result);setError(null);
  }catch(e){setInvoice(null);setError(e instanceof Error?e.message:"INVALID_SAMPLE_INVOICE");}
 };
 return <><AppHeader title={t(locale,"merchantDashboard")} back={back}/><MobileScroll><LabBanner locale={locale}/>
  <View style={styles.card}><Text style={styles.cardTitle}>Fictional merchant invoice</Text>
   <LabTextInput label="Sample description" value={description} onChange={setDescription}/>
   <LabTextInput label="Unit amount (BDT)" value={unit} onChange={setUnit} keyboardType="numeric"/>
   <LabTextInput label="Quantity" value={quantity} onChange={setQuantity} keyboardType="numeric"/>
   <LabButton label={t(locale,"prepare")} onPress={prepare}/>
   {error?<WarningNote message={error}/>:null}
  </View>
  {invoice?<View style={styles.card}>
   <Text style={styles.cardTitle}>{invoice.description}</Text>
   <ValueLine label="Quantity" value={String(invoice.quantity)}/>
   <ValueLine label="Unit price" value={formatBDT(invoice.unitPricePoisha,locale)}/>
   <ValueLine label={t(locale,"total")} value={formatBDT(invoice.totalPoisha,locale)} important/>
   <Text style={styles.tiny}>{invoiceToDescription(invoice,locale)}</Text>
   <WarningNote message="Sample invoice was not sent. No payment link, merchant capture or settlement exists."/>
  </View>:null}
  <View style={styles.card}><Text style={styles.cardTitle}>Merchant capabilities</Text>
   {Object.entries(capabilities).map(([label,available])=><ValueLine key={label} label={label} value={available?"DEMO":"DISABLED"}/>)}
  </View>
 </MobileScroll></>;
}
