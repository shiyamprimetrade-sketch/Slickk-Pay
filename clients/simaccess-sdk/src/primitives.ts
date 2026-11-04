/** Strict runtime parsing; JSON is never trusted merely because TypeScript compiled. */
import {failure, invariant} from "./errors.js";
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | {readonly [key: string]: JsonValue};
export type JsonRecord = Readonly<Record<string, unknown>>;
export function record(value: unknown): JsonRecord {
  invariant(value !== null && typeof value === "object" && !Array.isArray(value));
  const raw = value as Record<string, unknown>;
  invariant(Object.getPrototypeOf(raw) === Object.prototype || Object.getPrototypeOf(raw) === null);
  return raw;
}
export function required(value: JsonRecord, key: string): unknown {
  invariant(Object.prototype.hasOwnProperty.call(value, key));
  return value[key];
}
export function text(value: unknown, min = 0, max = 256): string {
  invariant(typeof value === "string" && value.length >= min && value.length <= max);
  invariant(!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value));
  return value;
}
export function literal<T extends string>(value: unknown, choices: readonly T[]): T {
  invariant(typeof value === "string" && choices.includes(value as T));
  return value as T;
}
export function boolean(value: unknown): boolean {
  invariant(typeof value === "boolean");
  return value;
}
export function integer(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  invariant(typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max);
  return value;
}
export function optionalText(value: unknown, min = 0, max = 256): string | null {
  if (value === null || value === undefined) return null;
  return text(value, min, max);
}
export function list(value: unknown, max = 500): readonly unknown[] {
  invariant(Array.isArray(value) && value.length <= max);
  return value as readonly unknown[];
}
export function hex(value: unknown, size = 64): string {
  const s = text(value, size, size);
  invariant(new RegExp(`^[a-f0-9]{${size}}$`).test(s));
  return s;
}
export function exactKeys(value: JsonRecord, allowed: readonly string[], requiredKeys: readonly string[] = allowed): void {
  const names = Object.keys(value);
  invariant(names.every(name => allowed.includes(name)));
  invariant(requiredKeys.every(name => Object.prototype.hasOwnProperty.call(value, name)));
}
export function mapList<T>(value: unknown, parser: (item: unknown) => T, max = 100): readonly T[] {
  return Object.freeze(list(value, max).map(parser));
}
export function finiteDateEpoch(value: unknown): number {
  return integer(value, 1, 4_102_444_800);
}
export function safeIso(value: unknown): string {
  const s = text(value, 19, 40);
  invariant(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d/.test(s));
  invariant(Number.isFinite(Date.parse(s)));
  return s;
}
export function parseJson(body: string, maxBytes = 131072): unknown {
  if (body.length > maxBytes) throw failure("BODY_TOO_LARGE");
  try { return JSON.parse(body) as unknown; }
  catch { throw failure("UNTRUSTED_RESPONSE"); }
}
export function stableJson(value: JsonValue): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  const obj = value as Record<string, JsonValue>;
  return `{${Object.keys(obj).sort().map(k => `${JSON.stringify(k)}:${stableJson(obj[k] ?? null)}`).join(",")}}`;
}
export function noCredentialFields(value: unknown, depth = 0): void {
  invariant(depth <= 12);
  if (Array.isArray(value)) {for (const x of value) noCredentialFields(x, depth + 1); return;}
  if (value === null || typeof value !== "object") return;
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const name = key.toLowerCase();
    if (/(password|passwd|secret|private_key|card_no|pin_hash|raw_token)/.test(name))
      throw failure("PRIVACY_VIOLATION");
    noCredentialFields(item, depth + 1);
  }
}
export function validJsonDepth(value: unknown, maxDepth = 12, maxEntries = 10000): boolean {
  const walk = (v: unknown, depth: number): number => {
    if (depth > maxDepth) return maxEntries + 1;
    if (!v || typeof v !== "object") return 1;
    const entries = Object.values(v as Record<string, unknown>);
    if (entries.length > maxEntries) return maxEntries + 1;
    return 1 + entries.reduce<number>((n, x) => n + walk(x, depth + 1), 0);
  };
  return walk(value, 0) <= maxEntries;
}
export function nonemptyArray<T>(items: readonly T[]): readonly [T, ...T[]] {
  invariant(items.length > 0);
  return items as readonly [T, ...T[]];
}
