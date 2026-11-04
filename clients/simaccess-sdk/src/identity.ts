/** Synthetic-only account and actor semantics, never KYC or a banking identity. */
import {failure, invariant} from "./errors.js";
import {record, required, text, integer, boolean, literal, optionalText, mapList} from "./primitives.js";

export type Role = "customer" | "agent" | "merchant" | "operator";
export type ActorId = `sim_${string}`;
export type DeviceId = `sim_${string}`;
export interface IdentityView {
  readonly id: ActorId;
  readonly role: Role;
  readonly displayName: string;
  readonly maskedPhone: string | null;
  readonly simulation: true;
  readonly kycVerified: false;
}
export interface DeviceView {
  readonly id: DeviceId;
  readonly boundTo: ActorId;
  readonly trustedForDemo: boolean;
  readonly isHardwareVerified: false;
  readonly lastSeenAt: number | null;
}
export function syntheticId(value: unknown, kind = "identifier"): ActorId {
  void kind;
  const s = text(value, 8, 92);
  invariant(/^sim_[A-Za-z0-9_.:-]{4,88}$/.test(s));
  return s as ActorId;
}
export function syntheticDevice(value: unknown): DeviceId {
  return syntheticId(value, "device") as DeviceId;
}
export function parseRole(value: unknown): Role {
  return literal(value, ["customer", "agent", "merchant", "operator"] as const);
}
export function maskedMobile(value: string): string {
  const trimmed = value.replace(/[\s()-]/g, "");
  if (!/^(?:\+?880|0)1[3-9]\d{8}$/.test(trimmed)) return "[sample number hidden]";
  return `${trimmed.slice(0,3)}•••••${trimmed.slice(-3)}`;
}
export function safeDisplayName(value: unknown): string {
  const s = text(value, 1, 80).trim();
  invariant(s.length > 0 && !/[<>\r\n]/.test(s));
  return s;
}
export function parseIdentity(value: unknown): IdentityView {
  const item = record(value);
  const simulation = boolean(required(item, "simulation"));
  invariant(simulation === true);
  const verified = item["kyc_verified"] ?? item["kycVerified"] ?? false;
  invariant(verified === false, "UNSAFE_CAPABILITY");
  return Object.freeze({
    id: syntheticId(item["actor_id"] ?? item["id"]),
    role: parseRole(required(item, "role")),
    displayName: safeDisplayName(item["label"] ?? item["display_name"] ?? "Synthetic user"),
    maskedPhone: optionalText(item["masked_phone"] ?? null, 3, 40),
    simulation: true as const,
    kycVerified: false as const
  });
}
export function parseDevice(value: unknown): DeviceView {
  const item = record(value);
  invariant(item["hardware_verified"] !== true, "UNSAFE_CAPABILITY");
  const lastSeen = item["last_seen_at"];
  return Object.freeze({
    id: syntheticDevice(required(item, "device_id")),
    boundTo: syntheticId(required(item, "actor_id")),
    trustedForDemo: boolean(required(item, "trusted_for_demo")),
    isHardwareVerified: false as const,
    lastSeenAt: lastSeen === undefined || lastSeen === null ? null : integer(lastSeen, 0)
  });
}
export function parseDeviceList(value: unknown): readonly DeviceView[] {
  return mapList(value, parseDevice, 25);
}
export function roleMayViewOwnRecord(role: Role, resourceOwner: ActorId, requestor: ActorId): boolean {
  void role;
  return resourceOwner === requestor;
}
export function assertRole(identity: IdentityView, requiredRole: Role): void {
  if (identity.role !== requiredRole) throw failure("ROLE_FORBIDDEN");
}
export function canViewSampleAgentDirectory(role: Role): boolean {
  return role === "customer" || role === "agent" || role === "operator";
}
export function canReviewSampleCash(role: Role, operation: string): boolean {
  if (operation === "cash_in") return role === "customer" || role === "agent";
  if (operation === "cash_out") return role === "customer" || role === "agent";
  return false;
}
export function syntheticLabel(role: Role, locale: "en" | "bn"): string {
  const en = {customer: "Sample customer", agent: "Sample agent", merchant: "Sample merchant", operator: "Demo operator"};
  const bn = {customer: "নমুনা গ্রাহক", agent: "নমুনা এজেন্ট", merchant: "নমুনা ব্যবসায়ী", operator: "ডেমো অপারেটর"};
  return (locale === "bn" ? bn : en)[role];
}
export function validateRoleChange(previous: IdentityView, next: IdentityView): void {
  invariant(previous.id === next.id && previous.role === next.role, "ROLE_FORBIDDEN");
  invariant(next.simulation === true && next.kycVerified === false, "UNSAFE_CAPABILITY");
}
export function safeRecipientLabel(identity: IdentityView): string {
  const raw = identity.displayName;
  const words = raw.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "Sample recipient";
  if (words.length === 1) return `${words[0]?.slice(0, 1) ?? "S"}•••`;
  return `${words[0]?.slice(0, 1) ?? "S"}••• ${words[words.length - 1]?.slice(0, 1) ?? "R"}•••`;
}
