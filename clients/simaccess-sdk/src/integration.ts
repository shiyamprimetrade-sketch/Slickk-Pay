/** Explicit lab boot sequence; every step must succeed before private demo reads. */
import {failure} from "./errors.js";
import {createLabRuntime,type LabRuntime} from "./sdk-runtime.js";
import type {TransportAdapter} from "./transport.js";
import type {ActorId,DeviceId} from "./identity.js";
import {assertNoFinancialPermission} from "./policy.js";
export interface StartupInput {
 readonly baseURL:string;readonly adapter:TransportAdapter;
 readonly demoActor:ActorId;readonly demoDevice:DeviceId;
 readonly demoPin:string;readonly optInToFictionalData:true;
}
export interface StartupOutcome {
 readonly runtime:LabRuntime;readonly actor:ActorId;
 readonly readyForSampleViews:true;readonly actualFinancialServicesEnabled:false;
 readonly simulation:true;
}
export async function startLocalDemo(input:StartupInput):Promise<StartupOutcome>{
 if(input.optInToFictionalData!==true)throw failure("LAB_DISABLED");
 assertNoFinancialPermission();
 const runtime=createLabRuntime({baseURL:input.baseURL,adapter:input.adapter});
 try{
  const health=await runtime.client.health();
  if(!health.serving || health.acceptsMoney)throw failure("UNSAFE_CAPABILITY");
  const abilities=await runtime.client.capabilities();
  if(abilities.canPostMoney||abilities.externalBankConnected)throw failure("UNSAFE_CAPABILITY");
  const session=await runtime.client.startSession({actor_id:input.demoActor,
   device_id:input.demoDevice,demo_pin:input.demoPin});
  if(session.actor!==input.demoActor)throw failure("ROLE_FORBIDDEN");
  return Object.freeze({runtime,actor:input.demoActor,
   readyForSampleViews:true,actualFinancialServicesEnabled:false,simulation:true});
 }catch(error){runtime.dispose();throw error;}
}
export async function stopLocalDemo(outcome:StartupOutcome):Promise<void>{
 try{await outcome.runtime.client.endSession();}
 catch{outcome.runtime.dispose();}
 finally{outcome.runtime.dispose();}
}
export function neverBootstrapRemoteBanking(_input:StartupInput):never{
 throw failure("LAB_DISABLED");
}
