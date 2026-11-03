/** Navigation state is local presentation state and grants no financial authority. */
import type {Persona,ScreenState} from "./types.js";
export type ScreenName = "home"|"activity"|"agents"|"agent_detail"|"cash_quote"|"cash_in_quote"|"transfer_quote"|
 "merchant_quote"|"receipt"|"security"|"settings"|"support"|"agent_dashboard"|"merchant_dashboard"|
 "notifications"|"qr_preview"|"privacy"|"limitations";
export interface NavigationEntry extends ScreenState {readonly name:ScreenName;readonly params:Readonly<Record<string,string>>;}
export interface NavigatorSnapshot {readonly stack:readonly NavigationEntry[];readonly persona:Persona;readonly revision:number;}
const titles:Record<ScreenName,string>={
 home:"Dashboard",activity:"Activity",agents:"Sample agents",agent_detail:"Agent details",
 cash_quote:"Cash quote",cash_in_quote:"Cash-in preview",transfer_quote:"Transfer preview",merchant_quote:"Merchant preview",
 receipt:"Receipt",security:"Security",settings:"Settings",support:"Support",
 agent_dashboard:"Agent dashboard",merchant_dashboard:"Merchant dashboard",notifications:"Notices",
 qr_preview:"QR preview",privacy:"Privacy",limitations:"Sandbox limitations",
};
const roleRestrictions:Partial<Record<ScreenName,Persona>>={agent_dashboard:"agent",merchant_dashboard:"merchant"};
const allowed:Set<ScreenName>=new Set(Object.keys(titles) as ScreenName[]);
export function entry(name:ScreenName,params:Readonly<Record<string,string>>={}):NavigationEntry{
 if(!allowed.has(name))throw new Error("UNKNOWN_SCREEN");
 if(Object.keys(params).length>8)throw new Error("TOO_MANY_ROUTE_PARAMS");
 for(const [key,value] of Object.entries(params)){
  if(!/^[a-z_]{2,30}$/.test(key)||value.length>120||/[\u0000-\u001f]/.test(value))throw new Error("INVALID_ROUTE_PARAM");
 }
 return Object.freeze({name,title:titles[name],requiresRole:roleRestrictions[name]??null,
   simulation:true,params:Object.freeze({...params})});
}
export class LocalNavigator{
 private stack:NavigationEntry[];
 private revision=0;
 private persona:Persona;
 constructor(persona:Persona){this.persona=persona;this.stack=[entry("home")];}
 view():NavigatorSnapshot{return Object.freeze({stack:Object.freeze([...this.stack]),persona:this.persona,revision:this.revision});}
 current():NavigationEntry{return this.stack[this.stack.length-1]??entry("home");}
 push(name:ScreenName,params:Readonly<Record<string,string>>={}):NavigationEntry{
  const item=entry(name,params);
  if(item.requiresRole&&item.requiresRole!==this.persona)throw new Error("SCREEN_ROLE_FORBIDDEN");
  if(this.stack.length>=20)throw new Error("NAVIGATION_DEPTH_LIMIT");
  this.stack.push(item);this.revision++;return item;
 }
 replace(name:ScreenName,params:Readonly<Record<string,string>>={}):NavigationEntry{
  const item=entry(name,params);
  if(item.requiresRole&&item.requiresRole!==this.persona)throw new Error("SCREEN_ROLE_FORBIDDEN");
  this.stack[this.stack.length-1]=item;this.revision++;return item;
 }
 back():NavigationEntry{if(this.stack.length>1){this.stack.pop();this.revision++;}return this.current();}
 home():NavigationEntry{this.stack=[entry("home")];this.revision++;return this.current();}
 switchPersona(next:Persona):NavigationEntry{
  if(!["customer","agent","merchant"].includes(next))throw new Error("INVALID_PERSONA");
  this.persona=next;return this.home();
 }
 resolveLink(value:string):NavigationEntry{
  if(!value.startsWith("slickkpaylab://"))throw new Error("UNSAFE_DEEP_LINK");
  const url=new URL(value);
  if(url.username||url.password||url.hash)throw new Error("UNSAFE_DEEP_LINK");
  const screen=url.hostname as ScreenName;
  if(!allowed.has(screen))throw new Error("UNKNOWN_SCREEN");
  if(["cash_quote","cash_in_quote","transfer_quote","merchant_quote","security"].includes(screen))throw new Error("SENSITIVE_ROUTE_NOT_LINKABLE");
  const params:Record<string,string>={};
  url.searchParams.forEach((v,k)=>{if(k in params)throw new Error("DUPLICATE_ROUTE_PARAM");params[k]=v;});
  return this.push(screen,params);
 }
}
export function visibleTabs(persona:Persona):readonly ScreenName[]{
 if(persona==="agent")return Object.freeze(["home","agent_dashboard","activity","notifications","settings"]);
 if(persona==="merchant")return Object.freeze(["home","merchant_dashboard","activity","support","settings"]);
 return Object.freeze(["home","activity","agents","notifications","settings"]);
}
export function canNavigateTo(name:ScreenName,persona:Persona):boolean{return !!titles[name]&&(!roleRestrictions[name]||roleRestrictions[name]===persona);}
export function screenTitle(name:ScreenName):string{return titles[name];}
export function sanitizedExternalNavigation(raw:string):string|null{
 try{const u=new URL(raw);if(u.protocol!=="https:"||u.username||u.password||u.hash)return null;
  if(!["slickk.online","docs.expo.dev"].includes(u.hostname))return null;
  return u.toString();}catch{return null;}
}
