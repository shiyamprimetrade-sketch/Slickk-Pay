/** Memory-only snapshot cache; never a financial or authentication authority. */
import {failure,invariant} from "./errors.js";
import {syntheticId,type ActorId} from "./identity.js";
import {noCredentialFields,validJsonDepth} from "./primitives.js";
export interface CacheEntry<T> {
 readonly actor:ActorId;readonly category:string;readonly data:T;
 readonly storedAt:number;readonly expiresAt:number;
 readonly simulation:true;readonly authoritative:false;
}
export type CacheState="fresh"|"stale"|"missing";
export interface CacheRead<T>{readonly state:CacheState;readonly data:T|null;
 readonly updatedAt:number|null;readonly authoritative:false;}
export class SessionSnapshotCache {
 private readonly values=new Map<string,CacheEntry<unknown>>();
 private currentActor:ActorId|null=null;
 private readonly maxEntries:number;
 constructor(private readonly now:()=>number=()=>Date.now(),maxEntries=50){
  if(!Number.isSafeInteger(maxEntries)||maxEntries<1||maxEntries>500)throw failure("INVALID_INPUT");
  this.maxEntries=maxEntries;
 }
 bindActor(actor:ActorId):void{
  syntheticId(actor);
  if(this.currentActor!==actor){this.values.clear();this.currentActor=actor;}
 }
 private key(category:string):string{
  if(!/^[a-z_]{3,40}$/.test(category))throw failure("INVALID_INPUT");
  return `${this.currentActor??"none"}:${category}`;
 }
 save<T>(category:string,data:T,ttlMs=60_000):CacheEntry<T>{
  if(!this.currentActor)throw failure("UNAUTHORIZED");
  if(!Number.isSafeInteger(ttlMs)||ttlMs<1000||ttlMs>300000)throw failure("INVALID_INPUT");
  if(!validJsonDepth(data,12,3000))throw failure("UNTRUSTED_RESPONSE");
  noCredentialFields(data);
  const at=this.now();
  const entry=Object.freeze({actor:this.currentActor,category,data,
   storedAt:at,expiresAt:at+ttlMs,simulation:true as const,authoritative:false as const});
  this.values.delete(this.key(category));
  this.values.set(this.key(category),entry);
  while(this.values.size>this.maxEntries){
   const first=this.values.keys().next().value;
   if(first===undefined)break;
   this.values.delete(first);
  }
  return entry;
 }
 read<T>(category:string):CacheRead<T>{
  const entry=this.values.get(this.key(category));
  if(!entry)return Object.freeze({state:"missing",data:null,updatedAt:null,authoritative:false});
  if(entry.actor!==this.currentActor)throw failure("ROLE_FORBIDDEN");
  return Object.freeze({state:entry.expiresAt>this.now()?"fresh":"stale",
   data:entry.data as T,updatedAt:entry.storedAt,authoritative:false});
 }
 requireFresh<T>(category:string):T{
  const entry=this.read<T>(category);
  if(entry.state!=="fresh"||entry.data===null)throw failure("STALE_DATA");
  return entry.data;
 }
 listCategories():readonly string[]{
  return Object.freeze([...this.values.values()].map(e=>e.category));
 }
 clearCategory(category:string):void{this.values.delete(this.key(category));}
 clear():void{this.values.clear();}
 beforeBackground():void{this.values.clear();}
 afterLogout():void{this.values.clear();this.currentActor=null;}
 beforeDeviceChange():void{this.afterLogout();}
 mayUseAsBalanceProof():false{return false;}
 mayAuthorizeOffline():false{return false;}
 size():number{return this.values.size;}
 debug():Readonly<Record<string,string|number|boolean>>{
  return Object.freeze({bound:this.currentActor!==null,count:this.values.size,
   mode:"memory-only",simulation:true,authoritative:false});
 }
}
