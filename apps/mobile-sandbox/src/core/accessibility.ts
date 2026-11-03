/** Nonvisual clarity and tap-target policies for low-end Android phones. */
import type {Locale,Operation,Status,MoneyQuote,PaymentDraft} from "./types.js";
import {formatBDT} from "./money.js";
import {t,operationLabel,statusLabel} from "./locales.js";
export interface AccessibleAnnouncement {readonly text:string;readonly priority:"polite"|"assertive";readonly financialAction:false;}
export function quoteAccessibility(quote:MoneyQuote,locale:Locale):AccessibleAnnouncement{
 return {text:`${t(locale,"previewOnly")}. ${operationLabel(locale,quote.operation)}. `+
  `${t(locale,"principal")}: ${formatBDT(quote.principalPoisha,locale)}. `+
  `${t(locale,"fee")}: ${formatBDT(quote.customerFeePoisha,locale)}. `+
  `${t(locale,"total")}: ${formatBDT(quote.customerDebitPoisha,locale)}. ${t(locale,"serverRequired")}`,
  priority:"assertive",financialAction:false};
}
export function draftAccessibility(draft:PaymentDraft,locale:Locale):AccessibleAnnouncement{
 const warning=draft.state==="reviewed"?t(locale,"confirmNotAvailable"):t(locale,"previewOnly");
 return {text:`${operationLabel(locale,draft.operation)}. ${formatBDT(draft.principalPoisha,locale)}. ${warning}`,
  priority:"polite",financialAction:false};
}
export function statusAccessibility(status:Status,locale:Locale):AccessibleAnnouncement{
 return {text:`${statusLabel(locale,status)}. ${t(locale,"sampleOnly")}`,
  priority:status==="failed"||status==="review"?"assertive":"polite",financialAction:false};
}
export function headingLevels():Readonly<Record<string,1|2|3>>{
 return Object.freeze({screen:1,section:2,card:3,warning:2,receipt:2});
}
export function accessibleLabelForAmount(poisha:number,locale:Locale):string{
 return `${formatBDT(poisha,locale)} ${locale==="bn"?"কাল্পনিক টাকা":"fictional BDT"}`;
}
export function accessibleBalancePrivacy(hidden:boolean,locale:Locale):string{
 return hidden?(locale==="bn"?"নমুনা ব্যালেন্স লুকানো":"Sample balance hidden"):
 (locale==="bn"?"নমুনা ব্যালেন্স দেখানো হচ্ছে":"Sample balance visible");
}
export function summarizeTapTarget(width:number,height:number):{passes:boolean;minimum:number;reason:string}{
 const minimum=48;
 if(!Number.isFinite(width)||!Number.isFinite(height)||width<0||height<0)throw new Error("BAD_TAP_TARGET");
 return {passes:width>=minimum&&height>=minimum,minimum,reason:width>=minimum&&height>=minimum?"ACCESSIBLE":"TOO_SMALL"};
}
export function readableContrastRatio(foreground:string,background:string):number{
 const parse=(hex:string)=>{
  if(!/^#[0-9a-f]{6}$/i.test(hex))throw new Error("INVALID_COLOR");
  const components=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);
  const linear=components.map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4);
  return 0.2126*(linear[0]??0)+0.7152*(linear[1]??0)+0.0722*(linear[2]??0);
 };
 const l1=parse(foreground),l2=parse(background);
 return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
}
export function meetsReadableContrast(foreground:string,background:string,large=false):boolean{
 return readableContrastRatio(foreground,background)>=(large?3:4.5);
}
export function announceValidationIssues(issues:readonly {field:string;description:string}[],locale:Locale):AccessibleAnnouncement{
 const details=issues.slice(0,5).map(x=>`${x.field}: ${x.description}`).join(". ");
 return {text:`${t(locale,"required")}. ${details}`,priority:"assertive",financialAction:false};
}
export function keyboardInputForOperation(operation:Operation):"numeric"|"default"{
 return operation==="balance_inquiry"?"default":"numeric";
}
export function motionSafeDuration(reduceMotion:boolean,requestedMs:number):number{
 if(!Number.isFinite(requestedMs)||requestedMs<0||requestedMs>5000)throw new Error("BAD_MOTION_DURATION");
 return reduceMotion?0:Math.min(300,requestedMs);
}
export function accessibleReceiptFooter(locale:Locale):string{return `${t(locale,"receiptWarning")} ${t(locale,"simulationBanner")}`;}
export function layoutForWidth(width:number):"narrow"|"medium"|"wide"{
 if(!Number.isFinite(width)||width<240)throw new Error("UNSUPPORTED_SCREEN_WIDTH");
 return width<420?"narrow":width<760?"medium":"wide";
}
export function accessibilityTestChecklist():readonly {code:string;enforced:boolean}[]{
 return Object.freeze([
  {code:"SCREEN_READER_LABELS",enforced:true},{code:"NO_COLOR_ONLY_STATUS",enforced:true},
  {code:"MINIMUM_TAP_TARGET",enforced:true},{code:"BANGLA_ENGLISH",enforced:true},
  {code:"NO_CLIENT_FINANCIAL_CONFIRMATION",enforced:true},
  {code:"LIVE_DEVICE_ACCESSIBILITY_AUDIT",enforced:false},
 ]);
}
