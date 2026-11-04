/** Normalize the service capability contract. Missing safety gates fail closed. */
import {failure, invariant} from "./errors.js";
import {record, boolean, text, required} from "./primitives.js";
export interface SandboxCapabilities {
  readonly simulation: true;
  readonly realMoney: false;
  readonly externalBankConnected: false;
  readonly canPostMoney: false;
  readonly canIssueLoans: false;
  readonly canAuthorizeHandover: false;
  readonly acceptsDeposits: false;
  readonly offlinePosting: false;
  readonly supportsSampleQuotes: boolean;
  readonly supportsSampleSessions: boolean;
}
export const SAFE_CAPABILITIES: SandboxCapabilities = Object.freeze({
  simulation: true, realMoney:false, externalBankConnected:false,
  canPostMoney:false, canIssueLoans:false, canAuthorizeHandover:false,
  acceptsDeposits:false, offlinePosting:false, supportsSampleQuotes:true,
  supportsSampleSessions:true
});
const PROHIBITED_FLAGS = [
  "can_move_money", "can_pay", "payments_enabled", "cash_handover",
  "handover_authorized", "bank_connected", "real_money", "external_settlement",
  "accepts_deposits", "allows_cash_handover", "can_issue_loans", "production"
] as const;
export function assertNoLiveCapabilities(raw: unknown): void {
  const obj=record(raw);
  invariant(obj["simulation"] === true, "UNSAFE_CAPABILITY");
  for (const key of PROHIBITED_FLAGS) if (obj[key] === true) throw failure("UNSAFE_CAPABILITY");
  const nested = obj["features"];
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const features=record(nested);
    for (const key of PROHIBITED_FLAGS) if (features[key] === true) throw failure("UNSAFE_CAPABILITY");
  }
}
export function capabilities(raw: unknown): SandboxCapabilities {
  const obj=record(raw);
  assertNoLiveCapabilities(obj);
  return Object.freeze({
    ...SAFE_CAPABILITIES,
    supportsSampleQuotes: obj["quote_preview"] !== false,
    supportsSampleSessions: obj["synthetic_sessions"] !== false
  });
}
export interface HealthView {
  readonly simulation: true;
  readonly environment: "local_sandbox";
  readonly acceptsMoney: false;
  readonly serving: boolean;
}
export function health(raw: unknown): HealthView {
  const obj = record(raw);
  assertNoLiveCapabilities(obj);
  const serving = obj["healthy"] === true || obj["simulation"] === true;
  return Object.freeze({simulation:true,environment:"local_sandbox",acceptsMoney:false,serving});
}
export function ensureLocalDescriptor(baseURL: string): string {
  let url: URL;
  try {url=new URL(baseURL);} catch {throw failure("CROSS_ORIGIN_BLOCKED");}
  if (!((url.protocol === "http:" || url.protocol === "https:") &&
    ["localhost","127.0.0.1","[::1]"].includes(url.hostname) &&
    !url.username && !url.password && !url.search && !url.hash &&
    (url.pathname === "/" || url.pathname === ""))) throw failure("CROSS_ORIGIN_BLOCKED");
  if (url.port && (!/^\d{2,5}$/.test(url.port) || Number(url.port) > 65535))
    throw failure("CROSS_ORIGIN_BLOCKED");
  return url.origin;
}
export function environmentSummary(raw: unknown): string {
  const obj = record(raw);
  assertNoLiveCapabilities(obj);
  const version = obj["version"] === undefined ? "unknown" : text(obj["version"],1,60);
  return `fictional-local-lab/${version}`;
}
export function featureFlag(raw: unknown, name: string): boolean {
  const obj=record(raw);
  assertNoLiveCapabilities(obj);
  const value=obj[name];
  if (value === undefined) return false;
  return boolean(value);
}
export function denyUnsafeFeature(_flag: unknown): never {
  throw failure("SERVER_AUTHORITY_ABSENT");
}
