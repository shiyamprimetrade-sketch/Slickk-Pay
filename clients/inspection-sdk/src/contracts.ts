/** Strict parsers for untrusted read-only fictional ledger API responses. */
export type SourceTag = "SIMULATED_ONLY";
export type InterfaceScope = "READ_ONLY";
export type AccountKind = "customer" | "agent_float" | "agent_commission" | "merchant" |
  "platform_revenue" | "platform_treasury" | "escrow" | "sim_issuer";

export class ContractError extends Error {
  readonly code = "INVALID_SANDBOX_RESPONSE";
  constructor(readonly field: string) {
    super(`Unexpected sandbox data at ${field}`);
    this.name = "ContractError";
  }
}

function record(raw: unknown, path: string): Record<string, unknown> {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new ContractError(path);
  }
  return raw as Record<string, unknown>;
}

function requiredString(source: Record<string, unknown>, key: string,
                        max = 256): string {
  const value = source[key];
  if (typeof value !== "string" || !value || value.length > max) {
    throw new ContractError(key);
  }
  return value;
}

function checkedNumber(source: Record<string, unknown>, key: string,
                       opts: {min?: number, max?: number} = {}): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value) ||
      value < (opts.min ?? -Number.MAX_SAFE_INTEGER) ||
      value > (opts.max ?? Number.MAX_SAFE_INTEGER)) throw new ContractError(key);
  return value;
}

function bool(source: Record<string, unknown>, key: string): boolean {
  if (typeof source[key] !== "boolean") throw new ContractError(key);
  return source[key] as boolean;
}

function fakeOnly(source: Record<string, unknown>): void {
  if (source["simulation"] !== true) throw new ContractError("simulation");
}

function checkedArray(raw: unknown, key: string, limit = 500): unknown[] {
  if (!Array.isArray(raw) || raw.length > limit) throw new ContractError(key);
  return raw;
}

function objectOfNumbers(raw: unknown, key: string): Record<string, number> {
  const source = record(raw, key);
  const result: Record<string, number> = {};
  for (const [k, v] of Object.entries(source)) {
    if (typeof v !== "number" || !Number.isSafeInteger(v) || k.length > 64) {
      throw new ContractError(key);
    }
    result[k] = v;
  }
  return result;
}

export interface SandboxHealth {
  readonly simulation: true;
  readonly ledger_backend: "postgresql" | "sqlite";
  readonly checkouts_enabled: false;
  readonly connected_to_external_banks: false;
  readonly interface: InterfaceScope;
}

export function parseHealth(raw: unknown): SandboxHealth {
  const r = record(raw, "health");
  fakeOnly(r);
  if (r["ledger_backend"] !== "postgresql" && r["ledger_backend"] !== "sqlite") {
    throw new ContractError("ledger_backend");
  }
  if (r["checkouts_enabled"] !== false || r["connected_to_external_banks"] !== false ||
      r["interface"] !== "READ_ONLY") throw new ContractError("sandbox safety flags");
  return Object.freeze({simulation:true, ledger_backend:r["ledger_backend"],
                       checkouts_enabled:false,connected_to_external_banks:false,
                       interface:"READ_ONLY"});
}

export interface SandboxCapabilities {
  readonly simulation: true;
  readonly features: Readonly<Record<string, boolean>>;
}

export function parseCapabilities(raw: unknown): SandboxCapabilities {
  const r=record(raw,"capabilities");
  fakeOnly(r);
  const features=record(r["features"],"features");
  const result: Record<string,boolean> = {};
  for (const [key,value] of Object.entries(features)) {
    if (!/^[a-z_]{3,80}$/.test(key) || typeof value !== "boolean") {
      throw new ContractError("features");
    }
    result[key]=value;
  }
  for (const key of ["banks_connected", "external_settlement", "cash_handover", "microcredit_live"] as const) {
    if (result[key] !== false) throw new ContractError("cannot claim live features");
  }
  return Object.freeze({simulation:true,features:Object.freeze(result)});
}

export interface AccountRecord {
  readonly simulation: true;
  readonly account_id: string;
  readonly owner_id: string;
  readonly kind: AccountKind;
  readonly poisha: number;
  readonly version: number;
  readonly frozen: boolean;
}

const accountKinds = new Set<string>(["customer", "agent_float", "agent_commission",
   "merchant", "platform_revenue", "platform_treasury", "escrow", "sim_issuer"]);

function syntheticId(value: string, path: string): string {
  if (!/^sim_[A-Za-z0-9_:.-]{4,88}$/.test(value)) throw new ContractError(path);
  return value;
}

export function parseAccount(raw: unknown): AccountRecord {
  const r=record(raw,"account");
  fakeOnly(r);
  const kind=requiredString(r,"kind",40);
  if (!accountKinds.has(kind)) throw new ContractError("kind");
  return Object.freeze({
    simulation:true,
    account_id:syntheticId(requiredString(r,"account_id"),"account_id"),
    owner_id:syntheticId(requiredString(r,"owner_id"),"owner_id"),
    kind:kind as AccountKind,
    poisha:checkedNumber(r,"poisha"),
    version:checkedNumber(r,"version",{min:0}),
    frozen:bool(r,"frozen"),
  });
}

export interface ChainProof {
  readonly simulation: true;
  readonly count: number;
  readonly valid: boolean;
  readonly latest_hash: string;
  readonly total_debits: number;
  readonly total_credits: number;
  readonly mismatches: ReadonlyArray<string>;
}

export function parseChainProof(raw: unknown): ChainProof {
  const r=record(raw,"proof");
  fakeOnly(r);
  const mismatches=checkedArray(r["mismatches"],"mismatches").map((v,i)=>{
    if (typeof v!=="string" || v.length>160) throw new ContractError(`mismatches[${i}]`);
    return v;
  });
  const hash=requiredString(r,"latest_hash",64);
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new ContractError("latest_hash");
  const totals={debits:checkedNumber(r,"total_debits",{min:0}),
                credits:checkedNumber(r,"total_credits",{min:0})};
  const valid=bool(r,"valid");
  if (valid && (totals.debits!==totals.credits || mismatches.length!==0)) {
    throw new ContractError("contradictory ledger proof");
  }
  return Object.freeze({simulation:true,count:checkedNumber(r,"count",{min:0}),valid,
    latest_hash:hash,total_debits:totals.debits,total_credits:totals.credits,
    mismatches:Object.freeze(mismatches)});
}

export interface SecurityProof {
  readonly simulation: true;
  readonly valid: boolean;
  readonly count: number;
  readonly head_hash: string;
  readonly reasons: ReadonlyArray<string>;
}

export function parseSecurityProof(raw: unknown): SecurityProof {
  const r=record(raw,"security proof");
  fakeOnly(r);
  const hash=requiredString(r,"head_hash",64);
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new ContractError("head_hash");
  const reasons=checkedArray(r["reasons"],"reasons").map((value)=>{
    if (typeof value!=="string" || value.length>160) throw new ContractError("reasons");
    return value;
  });
  return Object.freeze({simulation:true,valid:bool(r,"valid"),
                       count:checkedNumber(r,"count",{min:0}),head_hash:hash,
                       reasons:Object.freeze(reasons)});
}

export interface AccountAudit {
  readonly simulation: true;
  readonly account_id: string;
  readonly owner_id: string;
  readonly kind: string;
  readonly opening: number;
  readonly posted_debits: number;
  readonly posted_credits: number;
  readonly observed: number;
  readonly matches: boolean;
  readonly evidence_hash: string;
}

export function parseAccountAudit(raw: unknown): AccountAudit {
  const r=record(raw,"audit");fakeOnly(r);
  const hash=requiredString(r,"evidence_hash",64);
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new ContractError("audit hash");
  const a=syntheticId(requiredString(r,"account_id"),"account_id");
  const owner=syntheticId(requiredString(r,"owner_id"),"owner_id");
  const debits=checkedNumber(r,"posted_debits",{min:0});
  const credits=checkedNumber(r,"posted_credits",{min:0});
  const opening=checkedNumber(r,"opening");
  const observed=checkedNumber(r,"observed");
  const matches=bool(r,"matches");
  if (matches && opening+credits-debits!==observed) throw new ContractError("audit arithmetic");
  return Object.freeze({simulation:true, account_id:a,owner_id:owner,
    kind:requiredString(r,"kind",40),opening,posted_debits:debits,
    posted_credits:credits,observed,matches,evidence_hash:hash});
}

export interface ReconciliationRecord {
  readonly simulation: true;
  readonly reference: string;
  readonly account_id: string;
  readonly date: string;
  readonly opening_poisha: number;
  readonly debit_poisha: number;
  readonly credit_poisha: number;
  readonly expected_poisha: number;
  readonly observed_poisha: number;
  readonly matched: boolean;
  readonly evidence_digest: string;
}

export function parseReconciliation(raw: unknown): ReconciliationRecord {
  const r=record(raw,"reconciliation");fakeOnly(r);
  const date=requiredString(r,"date",10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new ContractError("date");
  const hash=requiredString(r,"evidence_digest",64);
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new ContractError("evidence_digest");
  const opening=checkedNumber(r,"opening_poisha");
  const debits=checkedNumber(r,"debit_poisha",{min:0});
  const credits=checkedNumber(r,"credit_poisha",{min:0});
  const expected=checkedNumber(r,"expected_poisha");
  const observed=checkedNumber(r,"observed_poisha");
  const matched=bool(r,"matched");
  if (opening+credits-debits!==expected || (matched && observed!==expected)) {
    throw new ContractError("reconciliation arithmetic");
  }
  return Object.freeze({simulation:true,
    reference:syntheticId(requiredString(r,"reference"),"reference"),
    account_id:syntheticId(requiredString(r,"account_id"),"account_id"),date,
    opening_poisha:opening,debit_poisha:debits,credit_poisha:credits,
    expected_poisha:expected,observed_poisha:observed,matched,evidence_digest:hash});
}

export interface StatementRow {
  readonly event_id: string;
  readonly direction: "debit" | "credit";
  readonly amount: number;
  readonly created_at: string;
  readonly operation: string;
  readonly simulation: true;
}

export function parseStatement(raw: unknown): ReadonlyArray<StatementRow> {
  const r=record(raw,"statement");fakeOnly(r);
  return Object.freeze(checkedArray(r["rows"],"rows",250).map((source,index)=>{
    const item=record(source,`rows[${index}]`);
    fakeOnly(item);
    if (item["direction"]!=="debit" && item["direction"]!=="credit") {
      throw new ContractError("direction");
    }
    return Object.freeze({event_id:syntheticId(requiredString(item,"event_id"),"event_id"),
      direction:item["direction"],amount:checkedNumber(item,"amount",{min:1}),
      created_at:requiredString(item,"created_at",35),
      operation:requiredString(item,"operation",50),simulation:true});
  }));
}

export interface Dashboard {
  readonly simulation: true;
  readonly truth_in_advertising: string;
  readonly bank_settlement_confirmed: false;
  readonly cash_states: Readonly<Record<string,number>>;
  readonly redacted_security_events: number;
  readonly failed_notification_records: number;
  readonly account_liabilities_by_kind_poisha: Readonly<Record<string,number>>;
}

export function parseDashboard(raw: unknown): Dashboard {
  const r=record(raw,"dashboard");fakeOnly(r);
  if (r["bank_settlement_confirmed"]!==false) throw new ContractError("bank settlement claim");
  const caption=requiredString(r,"truth_in_advertising",128);
  if (!caption.toUpperCase().includes("FICTIONAL")) throw new ContractError("missing fictional marker");
  return Object.freeze({simulation:true,truth_in_advertising:caption,
    bank_settlement_confirmed:false,
    cash_states:Object.freeze(objectOfNumbers(r["cash_states"],"cash_states")),
    redacted_security_events:checkedNumber(r,"redacted_security_events",{min:0}),
    failed_notification_records:checkedNumber(r,"failed_notification_records",{min:0}),
    account_liabilities_by_kind_poisha:Object.freeze(objectOfNumbers(r["account_liabilities_by_kind_poisha"],"liabilities"))});
}
