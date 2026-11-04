/** Explicit compatibility gate for contract revisions and future server migrations. */
import {failure,invariant} from "./errors.js";
import {record,required,text,integer,mapList} from "./primitives.js";
export type ClientProtocol="simaccess-v4";
export interface ServerVersion {
 readonly name:string;readonly major:number;readonly minor:number;
 readonly patch:number;readonly simulation:true;
 readonly canMoveMoney:false;
}
export interface Compatibility {
 readonly supported:boolean;readonly server:ServerVersion;
 readonly clientMajor:4;readonly downgradeAllowed:false;
 readonly realMoneyEnabled:false;
}
export function parseServerVersion(raw:unknown):ServerVersion{
 const obj=record(raw);
 invariant(obj["simulation"]===true,"UNTRUSTED_RESPONSE");
 const rawText=text(required(obj,"version"),3,40);
 const result=/^(?:v)?(\d+)\.(\d+)\.(\d+)$/.exec(rawText);
 if(!result)throw failure("UNTRUSTED_RESPONSE");
 const major=integer(Number(result[1]),0,99);
 const minor=integer(Number(result[2]),0,999);
 const patch=integer(Number(result[3]),0,999);
 return Object.freeze({name:rawText,major,minor,patch,simulation:true,canMoveMoney:false});
}
export function compatible(server:ServerVersion):Compatibility{
 return Object.freeze({supported:server.major===4,server,clientMajor:4,
  downgradeAllowed:false,realMoneyEnabled:false});
}
export function requireCompatible(server:ServerVersion):void{
 if(!compatible(server).supported)throw failure("UNTRUSTED_RESPONSE");
}
export interface ContractManifest {
 readonly id:string;readonly state:"active"|"deprecated";
 readonly simulation:true;readonly isFinancialPosting:false;
}
export function parseContractManifest(raw:unknown):readonly ContractManifest[]{
 const o=record(raw);
 invariant(o["simulation"]===true,"UNTRUSTED_RESPONSE");
 return mapList(required(o,"contracts"),item=>{
  const v=record(item);
  return Object.freeze({id:text(required(v,"id"),3,80),
   state:v["deprecated"]===true?"deprecated" as const:"active" as const,
   simulation:true as const,isFinancialPosting:false as const});
 },100);
}
export function negotiationSummary(value:Compatibility):string{
 return value.supported?
  "Local sandbox contract is compatible. Real financial operations remain unavailable.":
  "The local sandbox contract cannot be trusted; refresh the client.";
}
export function noAutomaticProtocolDowngrade():false{return false;}
