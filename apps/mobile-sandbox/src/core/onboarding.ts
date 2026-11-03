/** Demo onboarding, no real KYC, identity enrollment, agent approval or money activation. */
import type {Locale,Persona,ActorId} from "./types.js";
import {fixtureActor} from "./fixtures.js";
import {normalizeBdPhone,maskPhone} from "./validation.js";
export type OnboardingPage="welcome"|"demo_role"|"privacy"|"consent"|"complete";
export interface OnboardingState {readonly page:OnboardingPage;readonly persona:Persona|null;readonly locale:Locale;
 readonly consent:boolean;readonly privacyAcknowledged:boolean;readonly simulation:true;readonly stage:number;readonly completedAt:string|null;}
const pages:readonly OnboardingPage[]=["welcome","demo_role","privacy","consent","complete"];
export function initialOnboarding(locale:Locale="bn"):OnboardingState{return Object.freeze({page:"welcome",persona:null,locale,consent:false,
 privacyAcknowledged:false,simulation:true,stage:0,completedAt:null});}
export function onboardingNext(state:OnboardingState,now:string):OnboardingState{
 if(state.page==="complete")return state;
 if(state.page==="demo_role"&&!state.persona)throw new Error("SELECT_DEMO_PERSONA");
 if(state.page==="privacy"&&!state.privacyAcknowledged)throw new Error("PRIVACY_ACK_REQUIRED");
 if(state.page==="consent"&&!state.consent)throw new Error("SIMULATION_CONSENT_REQUIRED");
 const next=state.stage+1;
 if(next>=pages.length)throw new Error("INVALID_ONBOARDING_STATE");
 return Object.freeze({...state,stage:next,page:pages[next]??"complete",
  completedAt:next===pages.length-1?now:null});
}
export function onboardingBack(state:OnboardingState):OnboardingState{
 if(state.page==="complete")throw new Error("ONBOARDING_COMPLETED");
 const next=Math.max(0,state.stage-1);
 return Object.freeze({...state,stage:next,page:pages[next]??"welcome"});
}
export function onboardingPersona(state:OnboardingState,persona:Persona):OnboardingState{
 if(state.page!=="demo_role"||!["customer","agent","merchant"].includes(persona))throw new Error("NOT_ROLE_STAGE");
 return Object.freeze({...state,persona});
}
export function onboardingPrivacy(state:OnboardingState,accepted:boolean):OnboardingState{
 if(state.page!=="privacy")throw new Error("NOT_PRIVACY_STAGE");
 return Object.freeze({...state,privacyAcknowledged:accepted});
}
export function onboardingConsent(state:OnboardingState,accepted:boolean):OnboardingState{
 if(state.page!=="consent")throw new Error("NOT_CONSENT_STAGE");
 return Object.freeze({...state,consent:accepted});
}
export function onboardingLanguage(state:OnboardingState,locale:Locale):OnboardingState{
 if(locale!=="en"&&locale!=="bn")throw new Error("UNSUPPORTED_LOCALE");
 return Object.freeze({...state,locale});
}
export function onboardingProgress(state:OnboardingState):{current:number;total:number;percent:number}{
 return {current:state.stage+1,total:pages.length,percent:Math.floor((state.stage+1)/pages.length*100)};
}
export function onboardingCompleted(state:OnboardingState):{ready:boolean;actorId:ActorId|null;simulated:true;kycVerified:false}{
 if(state.page!=="complete"||!state.consent||!state.privacyAcknowledged||!state.persona)return {ready:false,actorId:null,simulated:true,kycVerified:false};
 return {ready:true,actorId:fixtureActor(state.persona).id,simulated:true,kycVerified:false};
}
export function onboardingWarnings(locale:Locale):readonly string[]{
 return Object.freeze(locale==="bn"?["সব তথ্য কাল্পনিক।","কোনো আসল অর্থ লেনদেন করা যাবে না।","এটি পরিচয় যাচাই নয়।","এজেন্টকে পিন দেবেন না।"]:
 ["All records are synthetic fixtures.","You cannot send or receive real funds.","This is not KYC or account activation.","Never disclose a PIN to an agent."]);
}
export interface DemoIdentitySummary {readonly role:Persona;readonly displayName:string;readonly maskedNumber:string;readonly synthetic:true;readonly kycVerified:false;}
export function demoIdentitySummary(persona:Persona):DemoIdentitySummary{
 const person=fixtureActor(persona);
 return Object.freeze({role:persona,displayName:person.name,maskedNumber:maskPhone(person.phone),synthetic:true,kycVerified:false});
}
export function optionalPhonePreview(text:string):{valid:boolean;masked:string|null}{
 const normalized=normalizeBdPhone(text);
 return normalized.ok?{valid:true,masked:maskPhone(normalized.value)}:{valid:false,masked:null};
}
export function futureRegistrationRequirements():readonly {code:string;implemented:false}[]{
 return Object.freeze([
  {code:"LICENSED_ENTITY_AND_KYC_SCOPE",implemented:false},
  {code:"SERVER_SIDE_PHONE_OTP",implemented:false},
  {code:"RISK_REVIEW_AND_CUSTOMER_CONSENT",implemented:false},
  {code:"DATA_RESIDENCY_AND_RETENTION",implemented:false},
  {code:"AGENT_BUSINESS_LOCATION_VERIFICATION",implemented:false},
  {code:"SECURE_ACCOUNT_RECOVERY",implemented:false},
 ]);
}
export function onboardingIsPrivate(state:OnboardingState):boolean{
 return state.simulation===true&&state.completedAt!==null&&state.persona!==null;
}
