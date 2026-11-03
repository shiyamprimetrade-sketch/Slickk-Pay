/** Low-risk preferences only; never stores financial balances or authentication tokens. */
import type {Locale,Persona} from "./types.js";
import {safeStoragePolicy} from "./security.js";
export interface DisplayPreferences {readonly locale:Locale;readonly highContrast:boolean;readonly textScale:1|1.15|1.3|1.5;
 readonly reduceMotion:boolean;readonly showFictionalAmounts:boolean;readonly persona:Persona;}
export interface PreferenceChange {readonly name:keyof DisplayPreferences;readonly before:unknown;readonly after:unknown;readonly at:string;}
export const DEFAULT_PREFERENCES:DisplayPreferences=Object.freeze({locale:"bn",highContrast:false,
 textScale:1.15,reduceMotion:false,showFictionalAmounts:true,persona:"customer"});
export function normalizePreferences(input:unknown):DisplayPreferences{
 if(!input||typeof input!=="object"||Array.isArray(input))return DEFAULT_PREFERENCES;
 const x=input as Record<string,unknown>;
 const locale=x["locale"]==="en"||x["locale"]==="bn"?x["locale"]:"bn";
 const persona=x["persona"]==="customer"||x["persona"]==="agent"||x["persona"]==="merchant"?x["persona"]:"customer";
 const scale=[1,1.15,1.3,1.5].includes(Number(x["textScale"]))?Number(x["textScale"]) as DisplayPreferences["textScale"]:1.15;
 return Object.freeze({locale,persona,textScale:scale,
  highContrast:x["highContrast"]===true,reduceMotion:x["reduceMotion"]===true,
  showFictionalAmounts:x["showFictionalAmounts"]!==false});
}
export function changedPreferences(before:DisplayPreferences,after:DisplayPreferences,now:string):readonly PreferenceChange[]{
 if(!Number.isFinite(Date.parse(now)))throw new Error("BAD_CHANGE_TIME");
 const keys=Object.keys(before) as (keyof DisplayPreferences)[];
 return Object.freeze(keys.filter(key=>before[key]!==after[key]).map(name=>({name,before:before[name],after:after[name],at:now})));
}
export function persistablePreferences(preferences:DisplayPreferences):Readonly<Record<string,string|number|boolean>>{
 return Object.freeze({locale:preferences.locale,highContrast:preferences.highContrast,
  textScale:preferences.textScale,reduceMotion:preferences.reduceMotion});
}
export function privacyAuditPreferences(values:Record<string,unknown>):readonly string[]{
 const problems:string[]=[];
 for(const key of Object.keys(values)){
  const policy=safeStoragePolicy(key);
  if(!policy.persist)problems.push(`UNSAFE_STORAGE:${key}`);
 }
 return Object.freeze(problems);
}
export function accessibilityTextSize(base:number,preferences:DisplayPreferences):number{
 if(!Number.isFinite(base)||base<10||base>80)throw new Error("INVALID_FONT_SIZE");
 return Math.max(12,Math.min(96,Math.round(base*preferences.textScale)));
}
export function accessibleHitTarget(preferences:DisplayPreferences):number{return preferences.textScale>1.3?52:48;}
export function accessibilityPreferences(preferences:DisplayPreferences):Readonly<Record<string,string|number|boolean>>{
 return Object.freeze({highContrast:preferences.highContrast,reduceMotion:preferences.reduceMotion,
  textScale:preferences.textScale,minimumTouchTarget:accessibleHitTarget(preferences),
  liveMoneyEnabled:false});
}
export function preferenceColorPalette(preferences:DisplayPreferences):{background:string;surface:string;text:string;muted:string;accent:string;border:string;danger:string}{
 return preferences.highContrast?{background:"#FFFFFF",surface:"#FFFFFF",text:"#000000",muted:"#111111",accent:"#002A78",border:"#000000",danger:"#8B0000"}:
 {background:"#F4F7FA",surface:"#FFFFFF",text:"#13293D",muted:"#52677A",accent:"#1268AB",border:"#DCE4EB",danger:"#B1273D"};
}
export class LocalPreferenceStore{
 private current:DisplayPreferences;
 private readonly changes:PreferenceChange[]=[];
 constructor(initial:DisplayPreferences=DEFAULT_PREFERENCES){this.current=Object.freeze({...initial});}
 snapshot():DisplayPreferences{return this.current;}
 update(patch:Partial<DisplayPreferences>,now:string):DisplayPreferences{
  const next=normalizePreferences({...this.current,...patch});
  this.changes.push(...changedPreferences(this.current,next,now));
  this.current=next;return next;
 }
 audit():readonly PreferenceChange[]{return Object.freeze([...this.changes]);}
 reset(now:string):DisplayPreferences{return this.update(DEFAULT_PREFERENCES,now);}
}
export function localeFromDeviceLanguage(value:string):Locale{return value.toLowerCase().startsWith("bn")?"bn":"en";}
export function recommendReducedMotion(prefersReducedMotion:boolean,deviceBatteryLow:boolean):boolean{return prefersReducedMotion||deviceBatteryLow;}
export function preferenceReview(preferences:DisplayPreferences):readonly string[]{
 const notices:string[]=[];
 if(!preferences.showFictionalAmounts)notices.push("Fictional sample balances are hidden");
 if(preferences.highContrast)notices.push("High contrast enabled");
 if(preferences.reduceMotion)notices.push("Animations reduced");
 notices.push("No financial secrets or real balances are stored");
 return Object.freeze(notices);
}
