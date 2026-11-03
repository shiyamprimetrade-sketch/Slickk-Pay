/** On-device lifecycle and resource policy. Never assumes a hardware security attestation. */
import type {UiNetwork,Locale} from "./types.js";
export type Lifecycle="foreground"|"background"|"inactive";
export interface DeviceObservation {readonly lifecycle:Lifecycle;readonly network:UiNetwork;readonly batteryLow:boolean;
 readonly lowMemory:boolean;readonly screenReader:boolean;readonly reduceMotion:boolean;readonly secureKeystoreVerified:boolean;
 readonly observedAt:string;readonly simulation:true;}
export interface DeviceRecommendation {readonly code:string;readonly priority:"low"|"medium"|"high";readonly action:string;readonly financialPostingAllowed:false;}
export function newDeviceObservation(value:Partial<DeviceObservation>,at:string):DeviceObservation{
 if(!Number.isFinite(Date.parse(at)))throw new Error("INVALID_DEVICE_CLOCK");
 return Object.freeze({lifecycle:value.lifecycle??"foreground",network:value.network??"offline",
  batteryLow:value.batteryLow??false,lowMemory:value.lowMemory??false,
  screenReader:value.screenReader??false,reduceMotion:value.reduceMotion??false,
  secureKeystoreVerified:false,observedAt:at,simulation:true});
}
export function recommendedDeviceActions(state:DeviceObservation):readonly DeviceRecommendation[]{
 const recommendations:DeviceRecommendation[]=[];
 if(state.lifecycle!=="foreground")recommendations.push({code:"BACKGROUND",priority:"high",action:"Lock demo session and hide sample balances",financialPostingAllowed:false});
 if(state.network==="offline")recommendations.push({code:"OFFLINE",priority:"medium",action:"Present local fixtures only",financialPostingAllowed:false});
 if(state.batteryLow)recommendations.push({code:"LOW_BATTERY",priority:"low",action:"Disable nonessential animations",financialPostingAllowed:false});
 if(state.lowMemory)recommendations.push({code:"LOW_MEMORY",priority:"medium",action:"Reduce rendered sample items",financialPostingAllowed:false});
 if(state.screenReader)recommendations.push({code:"ACCESSIBILITY",priority:"medium",action:"Use full accessible labels and explicit financial caveats",financialPostingAllowed:false});
 if(!state.secureKeystoreVerified)recommendations.push({code:"KEYSTORE_UNVERIFIED",priority:"high",action:"Do not store real identity tokens",financialPostingAllowed:false});
 return Object.freeze(recommendations);
}
export function maxVisibleSampleRows(device:DeviceObservation):number{return device.lowMemory?10:device.batteryLow?20:50;}
export function shouldUseMotion(device:DeviceObservation):boolean{return !device.lowMemory&&!device.batteryLow&&!device.reduceMotion;}
export function sessionMustLock(device:DeviceObservation):boolean{return device.lifecycle!=="foreground";}
export function simulatedNetworkStatus(device:DeviceObservation):{connectivity:string;serverConnected:false;paymentsAvailable:false}{
 return {connectivity:device.network,serverConnected:false,paymentsAvailable:false};
}
export function devicePrivacyRisks(device:DeviceObservation):readonly string[]{
 const risks:string[]=[];
 if(device.lifecycle!=="foreground")risks.push("BACKGROUND_EXPOSURE");
 if(!device.secureKeystoreVerified)risks.push("NO_HARDWARE_ATTESTATION");
 if(device.network==="limited")risks.push("UNRELIABLE_CONNECTION");
 if(device.lowMemory)risks.push("RESOURCE_PRESSURE");
 return Object.freeze(risks);
}
export function lifecycleLabel(lifecycle:Lifecycle,locale:Locale):string{
 const english:Record<Lifecycle,string>={foreground:"Active",background:"Background",inactive:"Inactive"};
 const bangla:Record<Lifecycle,string>={foreground:"সক্রিয়",background:"পটভূমি",inactive:"নিষ্ক্রিয়"};
 return (locale==="bn"?bangla:english)[lifecycle];
}
export function lowBandwidthAdvice(network:UiNetwork):readonly string[]{
 if(network==="online")return Object.freeze(["Never consider an HTTP response a bank settlement receipt."]);
 return Object.freeze(["Read-only fictional fixtures may be visible.","Do not queue a financial transaction.",
  "Wait for authoritative server status before any real-life decision."]);
}
export function appEventSecurityPolicy(event:"background"|"foreground"|"screenshot"|"network_change"|"memory_warning"):{lock:boolean;purgePrivateView:boolean;allowFinancialPost:false}{
 return {lock:event==="background"||event==="screenshot",purgePrivateView:event==="background"||event==="memory_warning",allowFinancialPost:false};
}
export function localDeviceCapabilityReport():Readonly<Record<string,boolean>>{
 return Object.freeze({hardwareKeyAttestation:false,realBiometricVerification:false,realCustomerKyc:false,
  realOfflineTransfers:false,realCashHandover:false,customerDemoUi:true,readOnlyFixtures:true});
}
