/** Dedicated parsing of synthetic profile and customer/agent summary data. */
import {failure,invariant} from "./errors.js";
import {record,required,text,boolean,integer,mapList} from "./primitives.js";
import {syntheticId,parseRole,type ActorId,type Role} from "./identity.js";
import {feePoisha,type Poisha} from "./money.js";
export interface DemoProfile {
 readonly id:ActorId;readonly role:Role;
 readonly title:string;readonly createdAt:number|null;
 readonly demoAccountCount:number;
 readonly simulation:true;readonly liveKycVerified:false;
 readonly canMoveMoney:false;
}
export function parseDemoProfile(raw:unknown):DemoProfile{
 const obj=record(raw);
 invariant(obj["simulation"]===true,"UNTRUSTED_RESPONSE");
 if(obj["can_move_money"]===true || obj["kyc_verified"]===true)throw failure("UNSAFE_CAPABILITY");
 const actor=obj["persona"]??obj["actor"];
 const roleSource=actor&&typeof actor==="object"?record(actor):obj;
 const name=obj["label"]??roleSource["label"]??"Synthetic person";
 const count=obj["account_count"]??obj["demo_account_count"]??0;
 return Object.freeze({id:syntheticId(roleSource["actor_id"]??roleSource["id"]),
  role:parseRole(required(roleSource,"role")),title:text(name,1,90),
  createdAt:obj["created_at"]===undefined?null:integer(obj["created_at"],1),
  demoAccountCount:integer(count,0,100),simulation:true,
  liveKycVerified:false,canMoveMoney:false});
}
export interface SampleBalanceView {
 readonly owner:ActorId;readonly amount:Poisha;
 readonly currency:"BDT";readonly simulation:true;
 readonly bankDeposit:false;readonly authoritative:false;
}
export function parseSyntheticBalances(raw:unknown,owner:ActorId):readonly SampleBalanceView[]{
 const obj=record(raw);
 invariant(obj["simulation"]===true,"UNTRUSTED_RESPONSE");
 const rows=obj["accounts"]??obj["sample_balances"]??[];
 return mapList(rows,value=>{
  const row=record(value);
  if(row["bank_deposit"]===true||row["authoritative"]===true)throw failure("UNSAFE_CAPABILITY");
  const expectedAccount=owner.replace(/^sim_/,"sim_account_");
  if(row["owner_id"]!==undefined && row["owner_id"]!==owner)throw failure("ROLE_FORBIDDEN");
  if(row["account_id"]!==undefined && row["account_id"]!==expectedAccount)throw failure("ROLE_FORBIDDEN");
  return Object.freeze({owner,amount:feePoisha(row["amount_poisha"]??row["balance_poisha"]??row["sample_balance_poisha"]??0),
   currency:"BDT" as const,simulation:true as const,
   bankDeposit:false as const,authoritative:false as const});
 },40);
}
export function requireDemoOwner(profile:DemoProfile,expected:ActorId):void{
 if(profile.id!==expected)throw failure("ROLE_FORBIDDEN");
}
export function demoProfileWarning(locale:"en"|"bn"):string{
 return locale==="bn"?"পরিচয়, হিসাব ও ব্যালেন্স কাল্পনিক — ব্যাংক হিসাব নয়।":
  "Identity, accounts and displayed balances are fictional, not bank deposits.";
}
export function noProfileAuthorizesPayment(_profile:DemoProfile):false{return false;}
