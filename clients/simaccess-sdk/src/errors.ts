/** Closed error taxonomy. Never reveal SQL text, sessions, tokens, or raw exceptions. */
export type ErrorCode =
  | "LAB_DISABLED" | "UNAUTHORIZED" | "SESSION_EXPIRED" | "SESSION_REVOKED"
  | "DEVICE_MISMATCH" | "ROLE_FORBIDDEN" | "INVALID_INPUT" | "NOT_FOUND"
  | "REQUEST_FINAL" | "QUOTE_EXPIRED" | "QUOTE_CHANGED" | "CONFLICT"
  | "RATE_LIMITED" | "UNTRUSTED_RESPONSE" | "NETWORK_UNAVAILABLE"
  | "CROSS_ORIGIN_BLOCKED" | "TIMEOUT" | "BODY_TOO_LARGE"
  | "SERVER_AUTHORITY_ABSENT" | "UNSAFE_CAPABILITY" | "CANCELLED"
  | "UNKNOWN_ERROR" | "INVALID_MONEY" | "STALE_DATA" | "PRIVACY_VIOLATION";

export interface PublicFailure {
  readonly code: ErrorCode;
  readonly retryable: boolean;
  readonly simulation: true;
  readonly message: string;
}

const FRIENDLY: Readonly<Record<ErrorCode, string>> = Object.freeze({
  LAB_DISABLED: "This fictional access lab is unavailable.",
  UNAUTHORIZED: "Your demo session is not authorized.",
  SESSION_EXPIRED: "Your demo session has expired.",
  SESSION_REVOKED: "Your demo session was ended.",
  DEVICE_MISMATCH: "A different demo device was supplied.",
  ROLE_FORBIDDEN: "This role cannot view the requested synthetic resource.",
  INVALID_INPUT: "The sample request is invalid.",
  NOT_FOUND: "The requested sample item was not found.",
  REQUEST_FINAL: "The sample request has already reached a final state.",
  QUOTE_EXPIRED: "The simulated quote has expired.",
  QUOTE_CHANGED: "The server quote must be reviewed again.",
  CONFLICT: "This simulated reference belongs to a different request.",
  RATE_LIMITED: "Too many demo requests; try again later.",
  UNTRUSTED_RESPONSE: "The server response failed safety checks.",
  NETWORK_UNAVAILABLE: "The local simulation service is unavailable.",
  CROSS_ORIGIN_BLOCKED: "Only the approved local simulation service is allowed.",
  TIMEOUT: "The local service took too long to respond.",
  BODY_TOO_LARGE: "The response exceeded the demo size limit.",
  SERVER_AUTHORITY_ABSENT: "This app cannot authorize or finalize money movement.",
  UNSAFE_CAPABILITY: "The response claimed an unavailable financial capability.",
  CANCELLED: "The operation was cancelled without posting money.",
  UNKNOWN_ERROR: "The demo request could not be completed.",
  INVALID_MONEY: "This fictional amount is not a valid integer value.",
  STALE_DATA: "The sample data is out of date and must be refreshed.",
  PRIVACY_VIOLATION: "The sample payload exposed disallowed personal information."
});
const CODES = new Set<ErrorCode>(Object.keys(FRIENDLY) as ErrorCode[]);
export function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === "string" && CODES.has(value as ErrorCode);
}
export class LabClientError extends Error {
  readonly code: ErrorCode;
  readonly retryable: boolean;
  readonly simulation = true as const;
  readonly httpStatus: number | null;
  constructor(code: ErrorCode, status: number | null = null) {
    super(FRIENDLY[code]);
    this.name = "LabClientError";
    this.code = code;
    this.retryable = code === "NETWORK_UNAVAILABLE" || code === "TIMEOUT" || code === "RATE_LIMITED";
    this.httpStatus = status;
  }
  publicResult(): PublicFailure {
    return Object.freeze({code: this.code, retryable: this.retryable,
      message: FRIENDLY[this.code], simulation: true});
  }
}
export function failure(code: ErrorCode, status?: number): LabClientError {
  return new LabClientError(code, status ?? null);
}
export function invariant(condition: unknown, code: ErrorCode = "UNTRUSTED_RESPONSE"): asserts condition {
  if (!condition) throw failure(code);
}
export function asClientError(value: unknown): LabClientError {
  if (value instanceof LabClientError) return value;
  if (value instanceof Error && value.name === "AbortError") return failure("TIMEOUT");
  return failure("UNKNOWN_ERROR");
}
export function fromHttp(status: number, serverCode: unknown): LabClientError {
  if (status === 401) return failure("UNAUTHORIZED", status);
  if (status === 403) return failure("ROLE_FORBIDDEN", status);
  if (status === 404) return failure("NOT_FOUND", status);
  if (status === 408 || status === 504) return failure("TIMEOUT", status);
  if (status === 409) return failure(isErrorCode(serverCode) ? serverCode : "CONFLICT", status);
  if (status === 422) return failure("INVALID_INPUT", status);
  if (status === 429) return failure("RATE_LIMITED", status);
  if (status === 503) return failure("LAB_DISABLED", status);
  return failure("UNKNOWN_ERROR", status);
}
export function safeNotice(code: ErrorCode, locale: "en" | "bn"): string {
  if (locale === "en") return FRIENDLY[code];
  const translations: Partial<Record<ErrorCode, string>> = {
    LAB_DISABLED: "ডেমো সেবা এখন বন্ধ আছে।",
    UNAUTHORIZED: "ডেমো সেশনে অনুমতি নেই।",
    SESSION_EXPIRED: "ডেমো সেশনের মেয়াদ শেষ।",
    DEVICE_MISMATCH: "ভিন্ন ডেমো ডিভাইস শনাক্ত হয়েছে।",
    NETWORK_UNAVAILABLE: "স্থানীয় ডেমো সেবা পাওয়া যাচ্ছে না।",
    SERVER_AUTHORITY_ABSENT: "এই অ্যাপ অর্থ লেনদেন অনুমোদন করতে পারে না।",
    UNTRUSTED_RESPONSE: "সার্ভার থেকে পাওয়া তথ্য নিরাপদ নয়।"
  };
  return translations[code] ?? FRIENDLY[code];
}
export function guardUnknown(value: unknown, code: ErrorCode = "UNKNOWN_ERROR"): never {
  void value;
  throw failure(code);
}
