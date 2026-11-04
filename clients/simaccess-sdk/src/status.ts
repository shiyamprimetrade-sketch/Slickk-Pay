/** Human-readable release-state evidence that cannot be mistaken for licensing. */
import {failure,invariant} from "./errors.js";
export type BuildStage="local_lab"|"automated_test"|"review_draft"|"staging_unverified";
export type EvidenceCategory="source_test"|"database_test"|"android_bundle"|
 "device_install"|"gateway_sandbox"|"provider_settlement"|"regulatory_review";
export interface StageEvidence {
 readonly category:EvidenceCategory;readonly verified:boolean;
 readonly reference:string|null;readonly simulation:true;
}
export interface ReleaseView {
 readonly stage:BuildStage;readonly checks:readonly StageEvidence[];
 readonly financeProductionAuthorized:false;readonly canProcessActualCash:false;
 readonly evidenceVerifiedCount:number;readonly simulation:true;
}
export function releaseView(stage:BuildStage,checks:readonly StageEvidence[]):ReleaseView{
 if(!["local_lab","automated_test","review_draft","staging_unverified"].includes(stage))
  throw failure("INVALID_INPUT");
 const unique=new Set<EvidenceCategory>();
 for(const check of checks){
  invariant(check.simulation===true,"UNTRUSTED_RESPONSE");
  if(unique.has(check.category))throw failure("CONFLICT");
  unique.add(check.category);
  if(check.reference!==null && !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/.+$/.test(check.reference))
   throw failure("INVALID_INPUT");
 }
 return Object.freeze({stage,checks:Object.freeze([...checks]),
  financeProductionAuthorized:false,canProcessActualCash:false,
  evidenceVerifiedCount:checks.filter(x=>x.verified).length,simulation:true});
}
export function outstandingEvidence(view:ReleaseView):readonly EvidenceCategory[]{
 const needed:EvidenceCategory[]=["source_test","database_test","android_bundle",
  "device_install","gateway_sandbox","provider_settlement","regulatory_review"];
 const complete=new Set(view.checks.filter(x=>x.verified).map(x=>x.category));
 return Object.freeze(needed.filter(x=>!complete.has(x)));
}
export function releaseWarning(view:ReleaseView,locale:"en"|"bn"):string{
 const remaining=outstandingEvidence(view).length;
 return locale==="bn"?`নমুনা প্রকল্প: ${remaining} ধরনের প্রমাণ এখনো বাকি। বাস্তব লেনদেন বন্ধ।`:
  `Simulation only: ${remaining} evidence categories remain. Real payments are disabled.`;
}
export function cannotDeclareLicensedBank(_view:ReleaseView):false{return false;}
export function cannotMergeToProductionBasedOnTests(_view:ReleaseView):false{return false;}
