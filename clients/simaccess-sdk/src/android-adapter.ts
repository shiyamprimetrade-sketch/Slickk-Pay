/** Framework-neutral adapter for Android foreground, connectivity and memory events. */
import {failure,invariant} from "./errors.js";
import {DeviceSafetyController,type DeviceEvent} from "./device.js";
import {OfflinePolicy} from "./offline.js";
import {SessionSnapshotCache} from "./cache.js";
export type AndroidLifecycle="active"|"background"|"inactive";
export type ConnectivityKind="connected"|"disconnected"|"limited";
export interface AndroidEvent{
 readonly type:"app_state"|"connectivity"|"memory_warning"|"screen_capture";
 readonly value:string;readonly at:number;
}
export interface AndroidAdapterState{
 readonly appVisible:boolean;readonly networkReady:boolean;
 readonly cacheRows:number;readonly demoSessionLocked:boolean;
 readonly financialPostsQueued:0;readonly simulation:true;
}
export class AndroidLabAdapter{
 private appState:AndroidLifecycle="inactive";
 private connectivity:ConnectivityKind="disconnected";
 private eventCount=0;
 constructor(private readonly device:DeviceSafetyController,
  private readonly offline:OfflinePolicy,private readonly cache:SessionSnapshotCache){}
 onAndroidEvent(event:AndroidEvent):AndroidAdapterState{
  invariant(Number.isSafeInteger(event.at)&&event.at>=0);
  this.eventCount++;
  if(event.type==="app_state"){
   if(!["active","background","inactive"].includes(event.value))throw failure("INVALID_INPUT");
   this.appState=event.value as AndroidLifecycle;
   if(event.value==="active")this.device.handle("foreground");
   else this.device.handle("background");
  }else if(event.type==="connectivity"){
   if(!["connected","disconnected","limited"].includes(event.value))throw failure("INVALID_INPUT");
   this.connectivity=event.value as ConnectivityKind;
   this.offline.transition({type:event.value==="connected"?"connected":
    event.value==="limited"?"timeout":"disconnected",at:event.at});
  }else if(event.type==="memory_warning"){
   this.cache.clear();this.device.handle("memory_pressure");
  }else if(event.type==="screen_capture"){
   this.device.handle("screenshot_risk");this.cache.clear();
  }
  return this.snapshot();
 }
 snapshot():AndroidAdapterState{
  return Object.freeze({appVisible:this.appState==="active",
   networkReady:this.connectivity==="connected",cacheRows:this.cache.size(),
   demoSessionLocked:this.device.snapshot().locked,
   financialPostsQueued:0,simulation:true});
 }
 historyCount():number{return this.eventCount;}
 beforeNetworkRetry():void{
  if(this.connectivity!=="connected")throw failure("NETWORK_UNAVAILABLE");
 }
 mayPostMoney():false{return false;}
 mayQueueOfflineTransfer():false{return false;}
 dispose():void{
  this.device.handle("background");this.cache.afterLogout();this.offline.beforeDeviceSuspend();
 }
}
