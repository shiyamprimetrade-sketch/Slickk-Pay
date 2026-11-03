/** Public simulated mobile contracts. Never treat any field as an actual bank asset. */
export type Simulation = true;
export type Locale = "en" | "bn";
export type Persona = "customer" | "agent" | "merchant";
export type Role = Persona | "support" | "reviewer";
export type MoneyUnit = "BDT";
export type AccountKind = "customer" | "agent_float" | "agent_commission" | "merchant";
export type UiNetwork = "online" | "offline" | "limited";
export type Operation = "transfer" | "cash_in" | "cash_out" | "merchant_payment" | "balance_inquiry";
export type DraftState = "editing" | "quoted" | "reviewed" | "expired" | "cancelled";
export type ServerState = "not_sent" | "not_authorized";
export type Status = "pending" | "review" | "cancelled" | "failed" | "completed";
export type Severity = "info" | "warning" | "critical";
export type NoticeCategory = "account" | "security" | "cash" | "merchant" | "system";
export type Approval = "not_requested" | "requires_server";
export type ConsentStatus = "not_requested" | "draft_only";
export type SupportState = "open" | "investigating" | "waiting" | "closed";
export type TransferKind = "same_network" | "agent_cash" | "merchant_checkout";
export type ISODate = string;
export type SyntheticId = `sim_${string}`;
export type ActorId = SyntheticId;
export type AccountId = SyntheticId;
export type MinorUnit = number;
export type Json = null | string | number | boolean | readonly Json[] | {readonly [key: string]: Json};
export interface Fictional { readonly simulation: true; readonly dataProvenance: "fixture" | "sandbox_server"; }
export interface Timestamped { readonly createdAt: ISODate; readonly updatedAt: ISODate; }
export interface Person extends Fictional {
  readonly id: ActorId;
  readonly role: Persona;
  readonly name: string;
  readonly phone: string;
  readonly locale: Locale;
  readonly verified: false;
  readonly displayArea: string;
}
export interface Account extends Fictional {
  readonly id: AccountId;
  readonly ownerId: ActorId;
  readonly kind: AccountKind;
  readonly poisha: MinorUnit;
  readonly currency: MoneyUnit;
  readonly frozen: boolean;
  readonly version: number;
}
export interface AgentProfile extends Fictional {
  readonly id: ActorId;
  readonly actorId: ActorId;
  readonly businessName: string;
  readonly locationLabel: string;
  readonly cashAvailablePoisha: number;
  readonly floatAccountId: AccountId;
  readonly commissionAccountId: AccountId;
  readonly serviceHours: string;
  readonly acceptingRequests: boolean;
  readonly qualityStatus: "sample_good" | "sample_review";
}
export interface MerchantProfile extends Fictional {
  readonly id: ActorId;
  readonly businessName: string;
  readonly category: string;
  readonly settlementAccountId: AccountId;
  readonly active: boolean;
}
export interface MoneyQuote extends Fictional {
  readonly operation: Operation;
  readonly principalPoisha: number;
  readonly customerFeePoisha: number;
  readonly taxPoisha: number;
  readonly customerDebitPoisha: number;
  readonly recipientCreditPoisha: number;
  readonly agentCommissionPoisha: number;
  readonly merchantFeePoisha: number;
  readonly basis: "unapproved_pilot_hypothesis";
  readonly currency: "BDT";
  readonly rateVersion: string;
  readonly expiresAt: ISODate;
}
export interface PaymentDraft extends Fictional, Timestamped {
  readonly id: SyntheticId;
  readonly ownerId: ActorId;
  readonly operation: Operation;
  readonly payeeId: ActorId | null;
  readonly agentId: ActorId | null;
  readonly merchantId: ActorId | null;
  readonly principalPoisha: number;
  readonly note: string;
  readonly state: DraftState;
  readonly quote: MoneyQuote | null;
  readonly approval: Approval;
  readonly consent: ConsentStatus;
  readonly serverState: ServerState;
  readonly revision: number;
}
export interface SyntheticTransaction extends Fictional {
  readonly id: SyntheticId;
  readonly ownerId: ActorId;
  readonly otherParty: string;
  readonly operation: Operation;
  readonly amountPoisha: number;
  readonly feePoisha: number;
  readonly currency: "BDT";
  readonly state: Status;
  readonly occurredAt: ISODate;
  readonly reference: string;
  readonly description: string;
}
export interface Notification extends Fictional {
  readonly id: SyntheticId;
  readonly actorId: ActorId;
  readonly category: NoticeCategory;
  readonly severity: Severity;
  readonly title: string;
  readonly message: string;
  readonly createdAt: ISODate;
  readonly readAt: ISODate | null;
  readonly deepLink: string | null;
}
export interface SupportCase extends Fictional, Timestamped {
  readonly id: SyntheticId;
  readonly ownerId: ActorId;
  readonly subject: string;
  readonly category: "payment" | "security" | "agent" | "technical";
  readonly description: string;
  readonly status: SupportState;
  readonly relatedTransactionId: SyntheticId | null;
  readonly history: readonly CaseEvent[];
}
export interface CaseEvent { readonly at: ISODate; readonly action: string; readonly detail: string; }
export interface ScreenState {readonly name: string; readonly title: string; readonly requiresRole: Persona | null; readonly simulation: true;}
export interface AppSnapshot extends Fictional {
  readonly actor: Person;
  readonly accounts: readonly Account[];
  readonly agents: readonly AgentProfile[];
  readonly merchants: readonly MerchantProfile[];
  readonly transactions: readonly SyntheticTransaction[];
  readonly notices: readonly Notification[];
  readonly supportCases: readonly SupportCase[];
  readonly network: UiNetwork;
  readonly updatedAt: ISODate;
}
export interface FetchStatus {
  readonly lastAttemptAt: ISODate | null;
  readonly lastSuccessAt: ISODate | null;
  readonly network: UiNetwork;
  readonly serverVerified: boolean;
  readonly stale: boolean;
  readonly source: "fixtures" | "sandbox_server";
}
export interface ValidationIssue { readonly field: string; readonly code: string; readonly description: string; }
export type Validation<T> = {readonly ok: true; readonly value: T} | {readonly ok: false; readonly issues: readonly ValidationIssue[]};
export interface FieldInfo {readonly label: string;readonly value: string;readonly sensitive: boolean;}
export interface ActionAvailability {readonly enabled: boolean;readonly reason: string;readonly needsServer: boolean;}
export interface ReceiptLine {readonly title: string; readonly value: string; readonly emphasis: boolean;}
export interface ReceiptData extends Fictional {readonly id: SyntheticId;readonly title: string;readonly issuedAt: ISODate;readonly lines: readonly ReceiptLine[];readonly disclaimer: string;readonly digest: string;}
export interface RiskFinding {readonly code: string; readonly severity: Severity; readonly label: string;readonly blocksSubmission: boolean;}
export type DeepReadonly<T> = T extends (...args: never[]) => unknown ? T : T extends readonly (infer U)[] ? ReadonlyArray<DeepReadonly<U>> : T extends object ? { readonly [P in keyof T]: DeepReadonly<T[P]> } : T;
