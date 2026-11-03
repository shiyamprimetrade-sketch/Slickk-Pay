/** Exact BDT operations for informational UI only. Backend remains authoritative. */
export type Currency = "BDT";
export type BdtLiteral = string & { readonly __brand: "BdtLiteral" };
export type MinorPoisha = bigint & { readonly __brand: "MinorPoisha" };

const MONEY_PATTERN = /^(0|[1-9][0-9]{0,11})(?:\.([0-9]{1,2}))?$/;
const LIMIT = 100000000000000n;

export class MoneyInputError extends Error {
  readonly code = "INVALID_BDT_INPUT";
  constructor(message: string) { super(message); this.name = "MoneyInputError"; }
}

export function assertMinor(value: bigint, allowNegative = false): MinorPoisha {
  if (value > LIMIT || value < (allowNegative ? -LIMIT : 0n)) {
    throw new MoneyInputError("Poisha outside bounded fictional pilot range");
  }
  return value as MinorPoisha;
}

export function parseBdt(raw: string): MinorPoisha {
  if (typeof raw !== "string") throw new MoneyInputError("Expected a BDT string");
  const match = MONEY_PATTERN.exec(raw);
  if (!match) throw new MoneyInputError("Use nonnegative BDT literal with at most two decimals");
  const whole = BigInt(match[1] ?? "0");
  const fraction = (match[2] ?? "").padEnd(2, "0");
  const minor = whole * 100n + BigInt(fraction || "0");
  return assertMinor(minor);
}

export function formatBdt(value: bigint, allowNegative = true): string {
  const valid = assertMinor(value, allowNegative);
  const abs = valid < 0n ? -valid : valid;
  const major = abs / 100n;
  const cents = (abs % 100n).toString().padStart(2, "0");
  return `${valid < 0n ? "-" : ""}${major}.${cents}`;
}

export function minorFromInteger(value: number): MinorPoisha {
  if (!Number.isSafeInteger(value)) throw new MoneyInputError("Integer minor unit required");
  return assertMinor(BigInt(value));
}

export function minorFromApi(value: unknown): MinorPoisha {
  if (typeof value === "number") return minorFromInteger(value);
  if (typeof value === "string" && /^(0|[1-9][0-9]{0,14})$/.test(value)) {
    return assertMinor(BigInt(value));
  }
  throw new MoneyInputError("Financial amount must be a safe integer or decimal integer string");
}

export function sumMinor(values: ReadonlyArray<bigint>): MinorPoisha {
  let total = 0n;
  for (const value of values) total = assertMinor(total + value, true);
  return assertMinor(total, true);
}

export function subtractMinor(a: bigint, b: bigint): MinorPoisha {
  return assertMinor(a - b, true);
}

export function feePpm(principal: bigint, ppm: number): MinorPoisha {
  assertMinor(principal);
  if (!Number.isSafeInteger(ppm) || ppm < 0 || ppm > 1_000_000) {
    throw new MoneyInputError("Rate must be integer parts per million");
  }
  const dividend = principal * BigInt(ppm);
  const result = dividend / 1_000_000n;
  const roundUp = dividend % 1_000_000n >= 500_000n ? 1n : 0n;
  return assertMinor(result + roundUp);
}

export interface VisibleAmount {
  readonly bdt: string;
  readonly currency: Currency;
  readonly simulation: true;
}

export function visibleAmount(poisha: bigint): VisibleAmount {
  return Object.freeze({ bdt: formatBdt(poisha), currency: "BDT", simulation: true });
}

export function cashoutPilotQuote(principal: bigint): {
  readonly principal: MinorPoisha;
  readonly fee: MinorPoisha;
  readonly commission: MinorPoisha;
  readonly total: MinorPoisha;
  readonly disclaimer: string;
} {
  assertMinor(principal);
  if (principal <= 0n) throw new MoneyInputError("Principal must be positive");
  const fee = feePpm(principal, 10990);
  const commission = feePpm(principal, 5500);
  if (commission > fee) throw new MoneyInputError("Pilot tariff is not self consistent");
  return Object.freeze({
    principal: assertMinor(principal), fee, commission,
    total: assertMinor(principal + fee),
    disclaimer: "FICTIONAL PILOT QUOTE - NOT AN APPROVED TARIFF",
  });
}

export function merchantPilotQuote(principal: bigint): {
  readonly principal: MinorPoisha;
  readonly merchantFee: MinorPoisha;
  readonly merchantNet: MinorPoisha;
  readonly simulation: true;
} {
  assertMinor(principal);
  const merchantFee = feePpm(principal, 4500);
  if (merchantFee >= principal) throw new MoneyInputError("Fee exceeds principal");
  return Object.freeze({principal: assertMinor(principal), merchantFee,
                        merchantNet: assertMinor(principal - merchantFee), simulation: true});
}

export function safeMinorDisplay(value: unknown): string {
  try { return formatBdt(minorFromApi(value)); }
  catch { return "--"; }
}
