/** Financial explanations and localization for low-bandwidth simulated clients. */
import { formatBdt } from "./money.js";
import type { AccountRecord, ChainProof, ReconciliationRecord,
  Dashboard, StatementRow } from "./contracts.js";

export type Locale = "bn" | "en";
export type MessageKey = "fictional" | "noRealFunds" | "readOnly" | "ledgerOk" |
  "ledgerBroken" | "verificationPending" | "reconciliationMatch" |
  "reconciliationReview" | "networkUnavailable" | "sessionExpired" |
  "refundUnavailable" | "cashUnconfirmed" | "noBankSettlement" |
  "feePilotOnly" | "notOfflineAuthorized" | "accountFrozen" |
  "accountActive" | "balanceLabel" | "statementLabel" | "disputeOpen" |
  "agentInventory" | "merchantProcessing" | "creditNotLive" |
  "contactSupport" | "retryLater" | "amountLabel";

const EN: Readonly<Record<MessageKey,string>> = Object.freeze({
  fictional:"Fictional-money simulation",
  noRealFunds:"No real money is held, transferred or settled.",
  readOnly:"Read-only inspection mode",
  ledgerOk:"Synthetic ledger checks passed",
  ledgerBroken:"Ledger mismatch: investigate before any further test posting",
  verificationPending:"Verification evidence is pending",
  reconciliationMatch:"Internal journal and account records match",
  reconciliationReview:"Internal discrepancy requires manual review",
  networkUnavailable:"Network unavailable. Do not assume a payment completed.",
  sessionExpired:"Your local test session is no longer valid.",
  refundUnavailable:"Real refunds are not available in this simulation.",
  cashUnconfirmed:"Physical cash handover was not verified.",
  noBankSettlement:"Gateway validation is not bank settlement.",
  feePilotOnly:"Pilot fees are hypotheses, not approved tariffs.",
  notOfflineAuthorized:"Offline data cannot authorize a financial transaction.",
  accountFrozen:"Synthetic account is frozen.",
  accountActive:"Synthetic account is enabled.",
  balanceLabel:"Fictional balance",
  statementLabel:"Fictional statement",
  disputeOpen:"A review case is open.",
  agentInventory:"Agent cash inventory is a test assertion, not verified bank cash.",
  merchantProcessing:"Merchant processing is simulated.",
  creditNotLive:"Real lending is disabled.",
  contactSupport:"Contact authorized support if this occurred in a live product.",
  retryLater:"Try again after checking the authoritative server response.",
  amountLabel:"Amount (BDT)",
});

const BN: Readonly<Record<MessageKey,string>> = Object.freeze({
  fictional:"কাল্পনিক অর্থের পরীক্ষামূলক সিমুলেশন",
  noRealFunds:"এখানে কোনো প্রকৃত অর্থ রাখা, পাঠানো বা নিষ্পত্তি করা হয় না।",
  readOnly:"শুধুমাত্র তথ্য দেখার পরীক্ষামূলক মোড",
  ledgerOk:"পরীক্ষামূলক লেজারের যাচাই সফল হয়েছে",
  ledgerBroken:"লেজারে অমিল: নতুন পরীক্ষা চালানোর আগে পর্যালোচনা করুন",
  verificationPending:"যাচাইয়ের প্রমাণ এখনো পাওয়া যায়নি",
  reconciliationMatch:"অভ্যন্তরীণ হিসাব ও লেজার মিলেছে",
  reconciliationReview:"অভ্যন্তরীণ অমিলের জন্য যাচাই প্রয়োজন",
  networkUnavailable:"নেটওয়ার্ক নেই। অর্থ পাঠানো সম্পন্ন হয়েছে ধরে নেবেন না।",
  sessionExpired:"পরীক্ষামূলক সেশনটির মেয়াদ শেষ হয়েছে।",
  refundUnavailable:"এই পরীক্ষায় প্রকৃত অর্থ ফেরত দেওয়া যায় না।",
  cashUnconfirmed:"নগদ অর্থ হস্তান্তর যাচাই করা হয়নি।",
  noBankSettlement:"পেমেন্ট যাচাই মানেই ব্যাংকে নিষ্পত্তি নয়।",
  feePilotOnly:"পরীক্ষামূলক ফি অনুমানমাত্র, অনুমোদিত হার নয়।",
  notOfflineAuthorized:"অফলাইন তথ্য দিয়ে লেনদেন অনুমোদন করা যাবে না।",
  accountFrozen:"পরীক্ষামূলক অ্যাকাউন্ট স্থগিত।",
  accountActive:"পরীক্ষামূলক অ্যাকাউন্ট সক্রিয়।",
  balanceLabel:"কাল্পনিক ব্যালেন্স",
  statementLabel:"কাল্পনিক হিসাব বিবরণী",
  disputeOpen:"পর্যালোচনার জন্য একটি অভিযোগ খোলা আছে।",
  agentInventory:"এজেন্টের নগদ তথ্য পরীক্ষামূলক; ব্যাংক-যাচাইকৃত নয়।",
  merchantProcessing:"মার্চেন্ট পেমেন্ট পরীক্ষামূলক।",
  creditNotLive:"প্রকৃত ঋণ কার্যক্রম বন্ধ আছে।",
  contactSupport:"বাস্তব সেবায় এমন হলে অনুমোদিত সহায়তার সঙ্গে যোগাযোগ করুন।",
  retryLater:"সার্ভারের নির্ভরযোগ্য উত্তর যাচাই করে আবার চেষ্টা করুন।",
  amountLabel:"পরিমাণ (টাকা)",
});

export function message(locale: Locale, key: MessageKey): string {
  return (locale === "bn" ? BN : EN)[key];
}

export interface CardModel {
  readonly headline: string;
  readonly subtitle: string;
  readonly severity: "info" | "warning" | "error";
  readonly simulation: true;
}

export function ledgerCard(proof: ChainProof, locale: Locale): CardModel {
  return Object.freeze({
    headline:message(locale, proof.valid ? "ledgerOk" : "ledgerBroken"),
    subtitle:`${proof.count} events, ${proof.mismatches.length} mismatches — ${message(locale,"fictional")}`,
    severity: proof.valid ? "info" : "error",
    simulation:true,
  });
}

export function balanceCard(account: AccountRecord, locale: Locale): CardModel {
  return Object.freeze({
    headline:`${message(locale,"balanceLabel")}: ৳${formatBdt(BigInt(account.poisha))}`,
    subtitle:message(locale,account.frozen ? "accountFrozen" : "accountActive"),
    severity:account.frozen ? "warning" : "info",
    simulation:true,
  });
}

export function reconciliationCard(row: ReconciliationRecord, locale: Locale): CardModel {
  return Object.freeze({
    headline:message(locale,row.matched ? "reconciliationMatch" : "reconciliationReview"),
    subtitle:`${row.date} — ${message(locale,"fictional")}`,
    severity:row.matched ? "info" : "error",
    simulation:true,
  });
}

export function operationCaution(locale: Locale, code: string): CardModel {
  const map: Readonly<Record<string,MessageKey>> = {
    NETWORK_UNAVAILABLE:"networkUnavailable",
    TIMEOUT:"verificationPending",
    HTTP_401:"sessionExpired",
    HTTP_503:"retryLater",
    LEDGER_MISMATCH:"ledgerBroken",
    CASH_HANDOVER_PENDING:"cashUnconfirmed",
    OFFLINE:"notOfflineAuthorized",
  };
  const key = map[code] ?? "retryLater";
  return Object.freeze({headline:message(locale,key),subtitle:message(locale,"noRealFunds"),
                        severity:"warning",simulation:true});
}

export function statementRows(rows: ReadonlyArray<StatementRow>, locale: Locale):
  ReadonlyArray<{readonly when:string;readonly name:string;readonly amount:string;
                  readonly side:"debit"|"credit";readonly simulation:true}> {
  return Object.freeze(rows.map(row=>Object.freeze({
    when:row.created_at,name:row.operation,
    amount:`৳${formatBdt(BigInt(row.amount))}`,
    side:row.direction,simulation:true,
  })));
}

export function dashboardOverview(data: Dashboard, locale: Locale): CardModel {
  return Object.freeze({
    headline:message(locale,"readOnly"),
    subtitle:`${data.redacted_security_events} security events; ${message(locale,"fictional")}`,
    severity:data.failed_notification_records > 0 ? "warning" : "info",
    simulation:true,
  });
}
