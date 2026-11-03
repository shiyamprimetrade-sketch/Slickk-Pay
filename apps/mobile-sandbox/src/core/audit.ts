/** Audit UI safety properties separately from a regulated independent financial audit. */
import type {AppSnapshot,PaymentDraft,MoneyQuote,Notification,Locale} from "./types.js";
import {auditPrivateSnapshot,piiRiskScore} from "./privacy.js";
import {validateTranslations} from "./locales.js";
import {verifyQuote} from "./money.js";
import {draftProblems} from "./drafts.js";
export interface UiAuditFinding {readonly code:string;readonly severity:"info"|"warning"|"critical";readonly explanation:string;}
export interface UiAuditReport {readonly verifiedLocalFixtures:boolean;readonly findings:readonly UiAuditFinding[];
 readonly simulation:true;readonly independentSecurityReview:false;readonly liveReleaseApproved:false;}
const critical=(code:string,explanation:string):UiAuditFinding=>({code,severity:"critical",explanation});
const warning=(code:string,explanation:string):UiAuditFinding=>({code,severity:"warning",explanation});
export function auditMobileSnapshot(snapshot:AppSnapshot):UiAuditReport{
 const findings:UiAuditFinding[]=[];
 for(const reason of auditPrivateSnapshot(snapshot))findings.push(critical(reason,"Snapshot lacks fixture-only provenance"));
 if(snapshot.actor.verified!==false)findings.push(critical("FAKE_KYC_CLAIM","Synthetic profiles must not imply KYC"));
 if(snapshot.accounts.some(x=>x.poisha<0||!Number.isSafeInteger(x.poisha)))findings.push(critical("INVALID_ACCOUNT_AMOUNT","Invalid minor units"));
 const references=new Set<string>();
 for(const tx of snapshot.transactions){
  if(references.has(tx.reference))findings.push(warning("DUPLICATE_DEMO_REFERENCE","Repeated fixture reference"));
  references.add(tx.reference);
 }
 if(snapshot.notices.some(n=>n.actorId!==snapshot.actor.id))findings.push(critical("NOTICE_DATA_LEAK","Cross-persona notice"));
 const translations=validateTranslations();
 for(const failure of translations)findings.push(warning("TRANSLATION_MISSING",failure));
 return Object.freeze({verifiedLocalFixtures:findings.filter(x=>x.severity==="critical").length===0,
  findings:Object.freeze(findings),simulation:true,independentSecurityReview:false,liveReleaseApproved:false});
}
export function auditDraft(draft:PaymentDraft,now:string):UiAuditReport{
 const findings:UiAuditFinding[]=[];
 for(const issue of draftProblems(draft,now))findings.push(warning(issue.code,issue.description));
 if(draft.serverState!=="not_sent")findings.push(critical("SERVER_STATE_CLAIM","Cannot claim a sent payment"));
 if(draft.state==="reviewed"&&draft.approval!=="requires_server")findings.push(critical("MISSING_SERVER_GATE","Server gate was bypassed"));
 return {verifiedLocalFixtures:findings.every(x=>x.severity!=="critical"),findings,
  simulation:true,independentSecurityReview:false,liveReleaseApproved:false};
}
export function auditQuote(quote:MoneyQuote,now:string):UiAuditReport{
 const findings:UiAuditFinding[]=[];
 if(!verifyQuote(quote,now))findings.push(critical("UNTRUSTED_QUOTE","Quote arithmetic or validity failed"));
 if(quote.basis!=="unapproved_pilot_hypothesis")findings.push(critical("UNKNOWN_RATE_POLICY","Expected a pilot price assumption"));
 return {verifiedLocalFixtures:findings.length===0,findings,
  simulation:true,independentSecurityReview:false,liveReleaseApproved:false};
}
export function auditNotice(notification:Notification):readonly UiAuditFinding[]{
 const issues:UiAuditFinding[]=[];
 const risk=piiRiskScore({title:notification.title,message:notification.message});
 if(risk.score)issues.push(warning("POSSIBLE_SENSITIVE_NOTICE",risk.reasons.join(",")));
 if(!notification.simulation)issues.push(critical("REAL_NOTICE_IN_DEMO","External notification not permitted"));
 return Object.freeze(issues);
}
export function auditDisclaimer(locale:Locale):string{
 return locale==="bn"?"এই নিরীক্ষা কেবল স্থানীয় ডেমো যাচাই, স্বাধীন নিরাপত্তা সার্টিফিকেশন নয়।":
  "Local demonstration checks only. Not an independent penetration test or compliance certification.";
}
export function summarizeUiAudit(audit:UiAuditReport):Readonly<Record<string,number|boolean>>{
 return Object.freeze({critical:audit.findings.filter(x=>x.severity==="critical").length,
  warnings:audit.findings.filter(x=>x.severity==="warning").length,
  info:audit.findings.filter(x=>x.severity==="info").length,
  verifiedLocalFixtures:audit.verifiedLocalFixtures,
  independentSecurityReview:false,liveReleaseApproved:false});
}
export function releaseGates():readonly {code:string;complete:boolean}[]{
 return Object.freeze([
  {code:"APP_ANDROID_DEVICE_TEST",complete:false},
  {code:"END_USER_AUTHENTICATION",complete:false},
  {code:"CUSTOMER_KYC",complete:false},
  {code:"AGENT_ONBOARDING",complete:false},
  {code:"BANKING_LICENSE_SCOPE",complete:false},
  {code:"LIVE_LEDGER_SECURITY",complete:false},
  {code:"PRODUCTION_PENETRATION_TEST",complete:false},
  {code:"PROVIDER_PAYMENT_VALIDATION",complete:false},
  {code:"ACTUAL_BANK_RECONCILIATION",complete:false},
 ]);
}
