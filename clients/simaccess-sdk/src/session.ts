/** Transient demo session. Never write bearer credentials to local storage. */
import {failure, invariant} from "./errors.js";
import {record, required, text, integer, literal} from "./primitives.js";
import {syntheticId, syntheticDevice, parseRole, type ActorId, type DeviceId, type Role} from "./identity.js";
export interface SessionView {
  readonly actor: ActorId;
  readonly role: Role;
  readonly expiresAt: number;
  readonly locked: boolean;
  readonly simulation: true;
  readonly balanceAuthority: false;
}
export interface SessionCreated {
  readonly actor: ActorId;
  readonly role: Role;
  readonly expiresAt: number;
  readonly bearer: string;
}
export function parseSessionCreated(value: unknown): SessionCreated {
  const obj=record(value);
  invariant(obj["simulation"] === true && obj["real_money"] === false, "UNSAFE_CAPABILITY");
  const bearer=text(required(obj,"token"),40,2048);
  invariant(/^[A-Za-z0-9_-]+$/.test(bearer));
  return Object.freeze({
    actor: syntheticId(required(obj,"actor")),
    role: parseRole(required(obj,"role")),
    expiresAt: integer(required(obj,"expires_at"),1,4_102_444_800),
    bearer
  });
}
export interface DeviceClock {
  readonly nowSeconds: () => number;
  readonly trustedClock: boolean;
}
export const SYSTEM_DEMO_CLOCK: DeviceClock={
  nowSeconds:()=>Math.floor(Date.now()/1000),trustedClock:false
};
export type SessionState="empty"|"active"|"expired"|"locked"|"revoked";
export class InMemorySession {
  private token: string | null=null;
  private device: DeviceId | null=null;
  private actor: ActorId | null=null;
  private role: Role | null=null;
  private expiration=0;
  private stateValue: SessionState="empty";
  private readonly callbacks=new Set<(state:SessionState)=>void>();
  constructor(private readonly clock:DeviceClock=SYSTEM_DEMO_CLOCK){}
  private transition(state:SessionState):void{
    this.stateValue=state;
    if(state!=="active")this.token=null;
    for(const callback of this.callbacks)callback(state);
  }
  subscribe(callback:(state:SessionState)=>void):()=>void{
    this.callbacks.add(callback);callback(this.status());
    return ()=>{this.callbacks.delete(callback);};
  }
  attach(created:SessionCreated, deviceId:DeviceId):SessionView{
    invariant(created.expiresAt>this.clock.nowSeconds(),"SESSION_EXPIRED");
    this.wipe();
    this.device=syntheticDevice(deviceId);
    this.actor=created.actor;
    this.role=created.role;
    this.expiration=created.expiresAt;
    this.token=created.bearer;
    this.transition("active");
    return this.view();
  }
  status():SessionState{
    if(this.stateValue==="active" && this.expiration<=this.clock.nowSeconds())this.transition("expired");
    return this.stateValue;
  }
  view():SessionView{
    if(this.status()!=="active" || this.actor===null || this.role===null)
      throw failure("SESSION_EXPIRED");
    return Object.freeze({actor:this.actor,role:this.role,expiresAt:this.expiration,
      locked:false,simulation:true,balanceAuthority:false});
  }
  withTransientHeaders<T>(work:(headers:Readonly<Record<string,string>>)=>T):T{
    if(this.status()!=="active" || !this.token || !this.device)throw failure("SESSION_EXPIRED");
    // The caller must execute synchronously; no URL, cache or logging may receive credentials.
    return work(Object.freeze({Authorization:`Bearer ${this.token}`,"X-Sim-Device":this.device}));
  }
  sameActor(actor:ActorId):boolean{
    return this.status()==="active" && actor===this.actor;
  }
  assertRole(role:Role):void{
    if(this.status()!=="active")throw failure("SESSION_EXPIRED");
    if(this.role!==role)throw failure("ROLE_FORBIDDEN");
  }
  assertDevice(device:DeviceId):void{
    if(this.status()!=="active")throw failure("SESSION_EXPIRED");
    if(this.device!==device)throw failure("DEVICE_MISMATCH");
  }
  beforeBackground():void{this.transition("locked");}
  afterScreenCaptureConcern():void{this.transition("locked");}
  notifyUnauthorized():void{this.transition("revoked");}
  logoutLocal():void{this.transition("revoked");}
  wipe():void{
    this.token=null;this.device=null;this.actor=null;this.role=null;
    this.expiration=0;this.stateValue="empty";
  }
  debug():Readonly<Record<string,unknown>>{
    return Object.freeze({state:this.status(),simulation:true,hasBearer:this.token!==null,
      actor:this.actor,expiresAt:this.expiration,canPostMoney:false});
  }
  mayReuseExpiredToken():false{return false;}
  isServerAuthoritative():false{return false;}
}
export interface SessionPolicy {
  readonly maxSessionAgeSeconds:number;
  readonly neverPersistTokens:true;
  readonly clearOnBackground:true;
  readonly clearOnScreenshotRisk:true;
  readonly allowOfflineAuthorization:false;
}
export const SESSION_POLICY:SessionPolicy=Object.freeze({
  maxSessionAgeSeconds:900,neverPersistTokens:true,clearOnBackground:true,
  clearOnScreenshotRisk:true,allowOfflineAuthorization:false
});
export function assertSessionCompatible(view:SessionView,actor:ActorId,requiredRole?:Role):void{
  invariant(view.simulation===true && view.balanceAuthority===false,"UNSAFE_CAPABILITY");
  if(view.actor!==actor)throw failure("ROLE_FORBIDDEN");
  if(requiredRole && view.role!==requiredRole)throw failure("ROLE_FORBIDDEN");
}
