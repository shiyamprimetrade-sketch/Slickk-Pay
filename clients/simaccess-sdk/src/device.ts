/** Device lifecycle policy for low-cost Android demo clients. */
import {failure,invariant} from "./errors.js";
import {syntheticDevice,type DeviceId,type ActorId} from "./identity.js";
import {InMemorySession} from "./session.js";
import {SessionSnapshotCache} from "./cache.js";
import {OfflinePolicy} from "./offline.js";
export type DeviceEvent="foreground"|"background"|"screenshare_started"|
 "screenshot_risk"|"memory_pressure"|"device_switched"|"session_revoked";
export interface DeviceSafetyView{
 readonly deviceId:DeviceId;
 readonly foreground:boolean;
 readonly hasSecureScreen:boolean;
 readonly locked:boolean;
 readonly canApproveMoney:false;
 readonly simulation:true;
}
export class DeviceSafetyController{
 private foreground=false;
 private secureScreen=false;
 private locked=true;
 private events:DeviceEvent[]=[];
 constructor(readonly deviceId:DeviceId,private readonly session:InMemorySession,
  private readonly cache:SessionSnapshotCache,private readonly offline:OfflinePolicy){
  syntheticDevice(deviceId);
 }
 handle(event:DeviceEvent):DeviceSafetyView{
  this.events.push(event);
  if(this.events.length>100)this.events.shift();
  if(event==="foreground")this.foreground=true;
  if(event==="background"){
   this.foreground=false;this.locked=true;
   this.session.beforeBackground();this.cache.beforeBackground();this.offline.beforeDeviceSuspend();
  }
  if(event==="screenshare_started"||event==="screenshot_risk"){
   this.locked=true;this.secureScreen=false;
   this.session.afterScreenCaptureConcern();this.cache.clear();
  }
  if(event==="memory_pressure")this.cache.clear();
  if(event==="device_switched"||event==="session_revoked"){
   this.locked=true;this.session.notifyUnauthorized();this.cache.afterLogout();
  }
  return this.snapshot();
 }
 setScreenProtected(enabled:boolean):void{
  this.secureScreen=enabled;
  if(!enabled)this.locked=true;
 }
 unlockSyntheticView():DeviceSafetyView{
  if(!this.foreground||!this.secureScreen||this.session.status()!=="active")
   throw failure("SESSION_EXPIRED");
  this.locked=false;
  return this.snapshot();
 }
 snapshot():DeviceSafetyView{
  return Object.freeze({deviceId:this.deviceId,foreground:this.foreground,
   hasSecureScreen:this.secureScreen,locked:this.locked,canApproveMoney:false,simulation:true});
 }
 isSensitiveViewAllowed():boolean{
  return this.foreground&&this.secureScreen&&!this.locked&&this.session.status()==="active";
 }
 maySubmitFinancialPost():false{return false;}
 history():readonly DeviceEvent[]{return Object.freeze([...this.events]);}
}
export interface DeviceRegistrationIntent{
 readonly actor:ActorId;readonly device:DeviceId;
 readonly purpose:"synthetic_view_only";readonly attested:false;
}
export function demoDeviceIntent(actor:ActorId,device:DeviceId):DeviceRegistrationIntent{
 return Object.freeze({actor,device,purpose:"synthetic_view_only",attested:false});
}
