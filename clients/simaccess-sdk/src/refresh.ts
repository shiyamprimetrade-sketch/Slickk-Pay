/** Bound concurrent GET refreshes and invalidate snapshots after preview mutations. */
import {failure,invariant} from "./errors.js";
export type ResourceKind="profile"|"activity"|"agents"|"quotes"|"requests"|"notices";
export interface RefreshState{
 readonly resource:ResourceKind;readonly inProgress:boolean;
 readonly successAt:number|null;readonly failureAt:number|null;
 readonly revision:number;readonly simulation:true;
 readonly authoritativeForPayment:false;
}
class Slot<T>{
 promise:Promise<T>|null=null;
 lastSuccessful:number|null=null;
 lastFailed:number|null=null;
 revision=0;
}
export class RefreshCoordinator{
 private readonly slots=new Map<ResourceKind,Slot<unknown>>();
 constructor(private readonly now:()=>number=()=>Date.now()){}
 private slot(kind:ResourceKind):Slot<unknown>{
  let s=this.slots.get(kind);
  if(!s){s=new Slot<unknown>();this.slots.set(kind,s);}
  return s;
 }
 async singleFlight<T>(kind:ResourceKind,fetcher:()=>Promise<T>):Promise<T>{
  const current=this.slot(kind);
  if(current.promise)return current.promise as Promise<T>;
  const work=Promise.resolve().then(fetcher).then(result=>{
   current.lastSuccessful=this.now();current.revision++;
   return result;
  }).catch((error:unknown)=>{
   current.lastFailed=this.now();throw error;
  }).finally(()=>{current.promise=null;});
  current.promise=work;
  return work;
 }
 invalidate(kind:ResourceKind):void{
  const s=this.slot(kind);
  s.lastSuccessful=null;s.revision++;
 }
 afterPreviewReview():void{this.invalidate("quotes");this.invalidate("requests");}
 afterPreviewCancel():void{this.invalidate("quotes");this.invalidate("requests");}
 afterSignOut():void{
  for(const kind of this.slots.keys())this.invalidate(kind);
 }
 status(kind:ResourceKind):RefreshState{
  const s=this.slot(kind);
  return Object.freeze({resource:kind,inProgress:s.promise!==null,
   successAt:s.lastSuccessful,failureAt:s.lastFailed,revision:s.revision,
   simulation:true,authoritativeForPayment:false});
 }
 all():readonly RefreshState[]{
  const names:ResourceKind[]=["profile","activity","agents","quotes","requests","notices"];
  return Object.freeze(names.map(x=>this.status(x)));
 }
 mayAuthorizeMoney():false{return false;}
}
