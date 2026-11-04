/** Owner-scoped aggregate sample snapshot assembled from independent reads. */
import {failure,invariant} from "./errors.js";
import type {ActorId,Role} from "./identity.js";
import type {SampleQuote} from "./quotes.js";
import type {ReviewedPreview} from "./requests.js";
import type {Notice} from "./notices.js";
import type {AgentPreview} from "./directory.js";
import type {ActivityRow} from "./activity.js";
export interface LocalAccountSnapshot{
 readonly actor:ActorId;readonly role:Role;
 readonly quotes:readonly SampleQuote[];readonly requests:readonly ReviewedPreview[];
 readonly agents:readonly AgentPreview[];readonly notices:readonly Notice[];
 readonly activity:readonly ActivityRow[];readonly createdAt:number;
 readonly simulation:true;readonly canPostMoney:false;
 readonly safeForFinancialAuthorization:false;
}
export function buildSnapshot(actor:ActorId,role:Role,data:{
 quotes?:readonly SampleQuote[];requests?:readonly ReviewedPreview[];
 agents?:readonly AgentPreview[];notices?:readonly Notice[];
 activity?:readonly ActivityRow[];
},createdAt:number):LocalAccountSnapshot{
 const quotes=data.quotes??[],requests=data.requests??[],agents=data.agents??[],
  notices=data.notices??[],activity=data.activity??[];
 if(quotes.some(x=>x.owner!==actor)||requests.some(x=>x.owner!==actor)||
  activity.some(x=>x.actor!==actor))throw failure("ROLE_FORBIDDEN");
 if(!Number.isSafeInteger(createdAt)||createdAt<0)throw failure("INVALID_INPUT");
 if(quotes.length>100||requests.length>100||agents.length>100||notices.length>100||activity.length>250)
  throw failure("BODY_TOO_LARGE");
 return Object.freeze({actor,role,quotes:Object.freeze([...quotes]),
  requests:Object.freeze([...requests]),agents:Object.freeze([...agents]),
  notices:Object.freeze([...notices]),activity:Object.freeze([...activity]),
  createdAt,simulation:true,canPostMoney:false,safeForFinancialAuthorization:false});
}
export function snapshotExpires(snapshot:LocalAccountSnapshot,now:number,ttlMs=60000):boolean{
 return now-snapshot.createdAt>=ttlMs;
}
export function snapshotCount(snapshot:LocalAccountSnapshot):Readonly<Record<string,number>>{
 return Object.freeze({quotes:snapshot.quotes.length,requests:snapshot.requests.length,
  agents:snapshot.agents.length,notices:snapshot.notices.length,activity:snapshot.activity.length});
}
export function snapshotAfterSignOut(_snapshot:LocalAccountSnapshot):null{return null;}
export function cannotUseSnapshotToSpend(_snapshot:LocalAccountSnapshot):never{
 throw failure("SERVER_AUTHORITY_ABSENT");
}
