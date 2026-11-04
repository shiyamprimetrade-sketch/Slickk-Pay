/** Exact synthetic BDT arithmetic. This never computes an authoritative payable fee. */
import {failure, invariant} from "./errors.js";
import {integer, record, required, boolean, text} from "./primitives.js";
export type Poisha = number & {readonly __poisha: unique symbol};
export type RatePpm = number & {readonly __ppm: unique symbol};
export interface ReadOnlyMoney {
  readonly amountPoisha: Poisha;
  readonly currency: "BDT";
  readonly simulation: true;
  readonly authoritativeForPosting: false;
}
export interface MoneyBreakdown {
  readonly principal: Poisha;
  readonly fee: Poisha;
  readonly total: Poisha;
  readonly taxUnverified: true;
  readonly pricingIsPilot: true;
  readonly postingAllowed: false;
}
export const MAX_MINOR = 50_000_000;
export function poisha(value: unknown, allowZero = false): Poisha {
  try {return integer(value, allowZero ? 0 : 1, MAX_MINOR) as Poisha;}
  catch {throw failure("INVALID_MONEY");}
}
export function feePoisha(value: unknown): Poisha {
  return poisha(value, true);
}
export function safeAdd(a: Poisha, b: Poisha): Poisha {
  const result = a + b;
  if (!Number.isSafeInteger(result) || result > MAX_MINOR) throw failure("INVALID_MONEY");
  return result as Poisha;
}
export function safeSubtract(a: Poisha, b: Poisha): Poisha {
  const result = a - b;
  if (result < 0 || !Number.isSafeInteger(result)) throw failure("INVALID_MONEY");
  return result as Poisha;
}
export function asPpm(value: unknown): RatePpm {
  return integer(value, 0, 1_000_000) as RatePpm;
}
export function roundHalfUp(numerator: bigint, denominator: bigint): bigint {
  invariant(numerator >= 0n && denominator > 0n, "INVALID_MONEY");
  return (2n * numerator + denominator) / (2n * denominator);
}
export function pilotEstimate(principal: Poisha, rate: RatePpm): Poisha {
  const amount = roundHalfUp(BigInt(principal) * BigInt(rate), 1_000_000n);
  if (amount > BigInt(MAX_MINOR)) throw failure("INVALID_MONEY");
  return Number(amount) as Poisha;
}
export function fromBdtText(input: string): Poisha {
  const s = input.trim();
  if (!/^(0|[1-9]\d{0,5})(?:\.\d{1,2})?$/.test(s)) throw failure("INVALID_MONEY");
  const [units = "0", fraction = ""] = s.split(".");
  const n = BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (n > BigInt(MAX_MINOR)) throw failure("INVALID_MONEY");
  return poisha(Number(n), true);
}
export function toBdtText(value: Poisha): string {
  const amount = poisha(value, true);
  const units = Math.floor(amount / 100);
  const fraction = (amount % 100).toString().padStart(2, "0");
  return `${units}.${fraction}`;
}
export function moneyLabel(value: Poisha, locale: "en" | "bn" = "en"): string {
  const txt = toBdtText(value);
  const translated = locale === "bn" ? txt.replace(/[0-9]/g, digit => "০১২৩৪৫৬৭৮৯"[Number(digit)] ?? digit) : txt;
  return `৳${translated}`;
}
export function parseReadOnlyMoney(raw: unknown): ReadOnlyMoney {
  const item = record(raw);
  invariant(item["simulation"] === true && item["can_move_money"] !== true, "UNSAFE_CAPABILITY");
  invariant(text(required(item, "currency")) === "BDT", "INVALID_MONEY");
  return Object.freeze({
    amountPoisha: poisha(required(item,"amount_poisha"), true),
    currency: "BDT" as const, simulation: true as const, authoritativeForPosting: false as const
  });
}
export function readBreakdown(raw: unknown): MoneyBreakdown {
  const obj = record(raw);
  invariant(boolean(required(obj, "simulation")) === true, "UNSAFE_CAPABILITY");
  const principal = poisha(required(obj, "principal_poisha"));
  const fee = feePoisha(required(obj, "fee_poisha"));
  const total = poisha(required(obj, "total_poisha"));
  invariant(total === safeAdd(principal,fee), "INVALID_MONEY");
  invariant(obj["tax_unverified"] === true, "UNSAFE_CAPABILITY");
  return Object.freeze({principal,fee,total,taxUnverified: true as const,
    pricingIsPilot: true as const,postingAllowed: false as const});
}
export function percentOfGross(fee: Poisha, gross: Poisha): string {
  if (gross === 0) return "0.00";
  const units = roundHalfUp(BigInt(fee) * 10000n, BigInt(gross));
  const n = units.toString().padStart(3,"0");
  return `${n.slice(0,-2)}.${n.slice(-2)}`;
}
export function notBankSettlement(value: unknown): boolean {
  if (!value || typeof value !== "object") return true;
  const obj = value as Record<string, unknown>;
  return obj["bank_settlement_proof"] !== true && obj["payment_proof"] !== true;
}
export function assertNoBalanceAuthorization(_amount: Poisha, _deviceOnline: boolean): never {
  throw failure("SERVER_AUTHORITY_ABSENT");
}
