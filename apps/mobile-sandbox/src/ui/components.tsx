/** Reusable React Native controls with accessible labeling and conspicuous lab status. */
import React from "react";
import {View,Text,Pressable,TextInput,ScrollView,ActivityIndicator,AccessibilityInfo} from "react-native";
import type {Locale,UiNetwork} from "../core/types.js";
import {t} from "../core/locales.js";
import {palette,styles} from "./styles.js";
export function LabBanner({locale,compact=false}:{locale:Locale;compact?:boolean}){
 return <View style={styles.banner} accessible accessibilityRole="alert">
   <Text style={styles.bannerTitle}>{t(locale,"simulationBanner")}</Text>
   {!compact?<Text style={styles.bannerText}>{t(locale,"notReal")}</Text>:null}
  </View>;
}
export function SectionCard({title,subtitle,children}:{title:string;subtitle?:string;children:React.ReactNode}){
 return <View style={styles.card} accessible={false}>
  <Text style={styles.cardTitle} accessibilityRole="header">{title}</Text>
  {subtitle?<Text style={styles.cardSubtitle}>{subtitle}</Text>:null}
  {children}
 </View>;
}
export function LabButton({label,onPress,variant="primary",disabled=false,warning}:{label:string;onPress:()=>void;
 variant?:"primary"|"secondary";disabled?:boolean;warning?:string}){
 const outlined=variant==="secondary";
 return <Pressable accessibilityRole="button" accessibilityLabel={label}
  accessibilityHint={warning??"Demonstration action only"}
  accessibilityState={{disabled}} disabled={disabled} onPress={onPress}
  style={[styles.button,outlined?styles.buttonSecondary:null,disabled?styles.buttonDisabled:null]}>
   <Text style={[styles.buttonText,outlined?styles.buttonSecondaryText:null]}>{label}</Text>
 </Pressable>;
}
export function ValueLine({label,value,important=false}:{label:string;value:string;important?:boolean}){
 return <View style={styles.row} accessible accessibilityLabel={`${label}, ${value}`}>
   <Text style={important?styles.label:styles.cardSubtitle}>{label}</Text>
   <Text style={important?styles.cardTitle:styles.body}>{value}</Text>
 </View>;
}
export function WarningNote({message}:{message:string}){
 return <View style={styles.warning} accessibilityRole="alert"><Text style={styles.warningText}>{message}</Text></View>;
}
export function LabTextInput({label,value,onChange,placeholder,keyboardType="default",multiline=false,maxLength=120}:{
 label:string;value:string;onChange:(next:string)=>void;placeholder?:string;keyboardType?:"default"|"numeric"|"phone-pad";
 multiline?:boolean;maxLength?:number}){
 return <View style={{gap:5}}>
  <Text style={styles.label}>{label}</Text>
  <TextInput accessibilityLabel={label} value={value} onChangeText={onChange} placeholder={placeholder}
   placeholderTextColor={palette.quiet} style={[styles.input,multiline?{minHeight:100,textAlignVertical:"top"}:null]}
   keyboardType={keyboardType} multiline={multiline} maxLength={maxLength}
   autoCorrect={false} autoCapitalize="none" />
 </View>;
}
export function ChoiceChips<T extends string>({choices,value,onChange}:{choices:readonly {value:T;label:string}[];value:T;onChange:(next:T)=>void}){
 return <View style={styles.segmented} accessibilityRole="radiogroup">
  {choices.map(choice=><Pressable key={choice.value} onPress={()=>onChange(choice.value)}
    accessibilityRole="radio" accessibilityState={{checked:choice.value===value}}
    style={[styles.chip,choice.value===value?styles.chipActive:null]}>
    <Text style={[styles.chipText,choice.value===value?styles.chipTextActive:null]}>{choice.label}</Text>
  </Pressable>)}
 </View>;
}
export function AppHeader({title,subtitle,back}:{title:string;subtitle?:string;back?:()=>void}){
 return <View style={styles.header}>
  {back?<Pressable onPress={back} accessibilityRole="button" accessibilityLabel="Back" style={{paddingVertical:6}}>
    <Text style={styles.link}>‹ Back</Text>
   </Pressable>:null}
  <Text accessibilityRole="header" style={styles.title}>{title}</Text>
  {subtitle?<Text style={styles.subtitle}>{subtitle}</Text>:null}
 </View>;
}
export function NetworkHint({network,locale}:{network:UiNetwork;locale:Locale}){
 const label=network==="offline"?t(locale,"offline"):network==="online"?t(locale,"online"):t(locale,"limited");
 return <Text style={styles.tiny}>{label} · {t(locale,"previewOnly")}</Text>;
}
export function BottomTabs({tabs,current,onSelect}:{tabs:readonly {name:string;title:string}[];current:string;onSelect:(name:string)=>void}){
 return <View style={styles.bottomBar} accessibilityRole="tablist">
  {tabs.map(tab=><Pressable key={tab.name} onPress={()=>onSelect(tab.name)}
    accessibilityRole="tab" accessibilityState={{selected:current===tab.name}}
    style={styles.bottomTab}><Text numberOfLines={2}
      style={[styles.bottomLabel,current===tab.name?styles.bottomActive:null]}>{tab.title}</Text></Pressable>)}
 </View>;
}
export function DemoTile({title,detail,onPress}:{title:string;detail:string;onPress:()=>void}){
 return <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`${title}. ${detail}`}
  style={styles.tile}><Text style={styles.tileTitle}>{title}</Text><Text style={styles.tileHint}>{detail}</Text></Pressable>;
}
export function SampleListRow({title,subtitle,trailing,onPress}:{title:string;subtitle:string;trailing?:string;onPress?:()=>void}){
 const content=<View style={{paddingVertical:9,gap:3,borderBottomWidth:1,borderBottomColor:palette.line}}>
  <View style={styles.row}><Text style={[styles.label,{flex:1}]}>{title}</Text>{trailing?<Text style={styles.status}>{trailing}</Text>:null}</View>
  <Text style={styles.tiny}>{subtitle}</Text>
 </View>;
 if(!onPress)return content;
 return <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={`${title}, ${subtitle}, ${trailing??""}`}>{content}</Pressable>;
}
export function MobileScroll({children}:{children:React.ReactNode}){
 return <ScrollView style={styles.scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.scrollInner,styles.container]}>
  {children}
 </ScrollView>;
}
export function LoadingView({label}:{label:string}){
 return <View style={styles.empty}><ActivityIndicator color={palette.primary}/><Text style={styles.emptyText}>{label}</Text></View>;
}
export function EmptyView({label}:{label:string}){
 return <View style={styles.empty}><Text style={styles.emptyText}>{label}</Text></View>;
}
export function HiddenBalance({hidden,amount}:{hidden:boolean;amount:string}){
 return <Text accessibilityLabel={hidden?"Amount hidden":"Fictional sample balance"} style={styles.value}>{hidden?"৳•••••":amount}</Text>;
}
export function AccessibilityAnnounce({message}:{message:string}){
 React.useEffect(()=>{void AccessibilityInfo.announceForAccessibility(message);},[message]);
 return null;
}
