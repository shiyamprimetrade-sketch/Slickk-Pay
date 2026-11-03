/** Read-only mobile health and capability diagnostics. No actual infrastructure status claims. */
import type {AppSnapshot,UiNetwork} from "./types.js";
import {fixtureIntegrity} from "./fixtures.js";
import {validateTranslations} from "./locales.js";
import {auditPrivateSnapshot} from "./privacy.js";
export interface ClientHealthReport {readonly build:"mobile-lab-cycle003";readonly simulation:true;
 readonly source:"fixtures";readonly checkedAt:string;readonly dataValid:boolean;readonly issues:readonly string[];
 readonly testsRunOnDevice:false;readonly realBankConnected:false;readonly canPostFunds:false;}
export function localHealthReport(snapshot:AppSnapshot,at:string):ClientHealthReport{
 if(!Number.isFinite(Date.parse(at)))throw new Error("INVALID_HEALTH_CLOCK");
 const issues=[...fixtureIntegrity(),...validateTranslations(),...auditPrivateSnapshot(snapshot)];
 return Object.freeze({build:"mobile-lab-cycle003",simulation:true,source:"fixtures",
  checkedAt:at,dataValid:issues.length===0,issues:Object.freeze(issues),testsRunOnDevice:false,
  realBankConnected:false,canPostFunds:false});
}
export function healthBadges(report:ClientHealthReport):readonly {label:string;status:"pass"|"fail"|"unverified"}[]{
 return Object.freeze([
  {label:"Synthetic sample data",status:report.dataValid?"pass":"fail"},
  {label:"Local schema and translations",status:report.issues.length===0?"pass":"fail"},
  {label:"Android device installation",status:"unverified"},
  {label:"Real bank connectivity",status:"unverified"},
  {label:"Financial authorization",status:"unverified"},
 ]);
}
export function mobileCapabilityAudit():Readonly<Record<string,boolean>>{
 return Object.freeze({hasSampleAccounts:true,hasSampleAgents:true,hasSampleMerchants:true,
  hasSampleReceipts:true,hasStrictFeeMath:true,hasBanglaEnglish:true,
  hasLocalQuoteReviews:true,hasOfflineSafety:true,hasAuthoritativeCustomerApi:false,
  hasRealIdentityKyc:false,hasLiveFinancialPosting:false,hasRealBankSettlement:false,
  hasNativeAndroidBuildProof:false});
}
export function reportConnectivity(network:UiNetwork):{network:UiNetwork;actualServerHealthUnknown:true;productionReady:false}{
 return {network,actualServerHealthUnknown:true,productionReady:false};
}
export function healthReportIsReadyForLivePayments(_report:ClientHealthReport):false{return false;}
export function healthText(report:ClientHealthReport):string{
 return `${report.build}: ${report.dataValid?"local fixtures pass":"local fixture issues"}; no live payments enabled`;
}
