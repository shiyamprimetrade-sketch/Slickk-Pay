/** Read-only, fail-closed HTTP transport to Slickk Pay fictional ledger inspector. */
import {
  type SandboxHealth, type SandboxCapabilities, type ChainProof,
  type SecurityProof, type AccountRecord, type AccountAudit,
  type ReconciliationRecord, type Dashboard, type StatementRow,
  parseHealth, parseCapabilities, parseChainProof, parseSecurityProof,
  parseAccount, parseAccountAudit, parseReconciliation, parseDashboard,
  parseStatement, ContractError,
} from "./contracts.js";

export type OperatorKeyProvider = () => string | Promise<string>;
export type FetchFunction = typeof fetch;

export class SandboxApiError extends Error {
  readonly simulation = true;
  constructor(readonly code: string, readonly httpStatus: number | null = null) {
    super(code);
    this.name = "SandboxApiError";
  }
}

export interface ClientOptions {
  readonly baseUrl: string;
  readonly fetcher?: FetchFunction;
  readonly operatorKey: OperatorKeyProvider;
  readonly timeoutMs?: number;
}

function validatedBaseUrl(raw: string): string {
  let url: URL;
  try { url = new URL(raw); }
  catch { throw new SandboxApiError("BAD_BASE_URL"); }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if ((url.protocol !== "https:" && !(local && url.protocol === "http:")) ||
      url.username || url.password || url.search || url.hash ||
      !["", "/"].includes(url.pathname)) {
    throw new SandboxApiError("UNSAFE_BASE_URL");
  }
  return url.origin;
}

function syntheticSegment(value: string, label: string): string {
  if (!/^sim_[A-Za-z0-9_:.-]{4,88}$/.test(value)) throw new SandboxApiError(`INVALID_${label}`);
  return encodeURIComponent(value);
}

function dateSegment(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new SandboxApiError("INVALID_DATE");
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.valueOf()) || date.toISOString().slice(0,10)!==value) {
    throw new SandboxApiError("INVALID_DATE");
  }
  return value;
}

function timeout(value: number | undefined): number {
  const n = value ?? 8000;
  if (!Number.isSafeInteger(n) || n < 500 || n > 30000) {
    throw new SandboxApiError("INVALID_TIMEOUT");
  }
  return n;
}

function parseJsonSafely(text: string): unknown {
  if (text.length > 1048576) throw new SandboxApiError("OVERSIZED_RESPONSE");
  try { return JSON.parse(text) as unknown; }
  catch { throw new SandboxApiError("INVALID_JSON"); }
}

export class ReadOnlySandboxClient {
  private readonly origin: string;
  private readonly fetcher: FetchFunction;
  private readonly keyProvider: OperatorKeyProvider;
  private readonly timeoutMs: number;
  readonly simulation = true;
  readonly interface = "READ_ONLY";

  constructor(options: ClientOptions) {
    this.origin = validatedBaseUrl(options.baseUrl);
    this.fetcher = options.fetcher ?? fetch;
    this.keyProvider = options.operatorKey;
    this.timeoutMs = timeout(options.timeoutMs);
    Object.freeze(this);
  }

  private async read(path: string, authenticated = true): Promise<unknown> {
    if (!path.startsWith("/sim/v2/") || path.includes("..") || path.includes("\\")) {
      throw new SandboxApiError("INVALID_PATH");
    }
    const requestHeaders = new Headers({
      Accept: "application/json",
      "Cache-Control": "no-store",
    });
    if (authenticated) {
      const secret = await this.keyProvider();
      if (typeof secret !== "string" || secret.length < 48 || secret.length > 4096) {
        throw new SandboxApiError("OPERATOR_KEY_UNAVAILABLE");
      }
      requestHeaders.set("X-Sim-Operator-Key", secret);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetcher(this.origin + path, {
        method:"GET",headers:requestHeaders,cache:"no-store",credentials:"omit",
        redirect:"error",signal:controller.signal,
      });
      if (!response.ok) {
        throw new SandboxApiError(`HTTP_${response.status}`, response.status);
      }
      if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
        throw new SandboxApiError("UNEXPECTED_CONTENT_TYPE");
      }
      return parseJsonSafely(await response.text());
    } catch(error: unknown) {
      if (error instanceof SandboxApiError) throw error;
      if (error instanceof ContractError) throw error;
      if (controller.signal.aborted) throw new SandboxApiError("TIMEOUT");
      throw new SandboxApiError("NETWORK_UNAVAILABLE");
    } finally { clearTimeout(timer); }
  }

  async health(): Promise<SandboxHealth> {
    return parseHealth(await this.read("/sim/v2/health",false));
  }

  async capabilities(): Promise<SandboxCapabilities> {
    return parseCapabilities(await this.read("/sim/v2/capabilities"));
  }

  async proof(): Promise<ChainProof> {
    return parseChainProof(await this.read("/sim/v2/proof"));
  }

  async securityProof(): Promise<SecurityProof> {
    return parseSecurityProof(await this.read("/sim/v2/security-proof"));
  }

  async account(accountId: string): Promise<AccountRecord> {
    return parseAccount(await this.read(`/sim/v2/accounts/${syntheticSegment(accountId,"ACCOUNT")}`));
  }

  async statement(accountId: string, limit = 100): Promise<ReadonlyArray<StatementRow>> {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 250) {
      throw new SandboxApiError("INVALID_STATEMENT_LIMIT");
    }
    return parseStatement(await this.read(
      `/sim/v2/accounts/${syntheticSegment(accountId,"ACCOUNT")}/statement?limit=${limit}`));
  }

  async accountAudit(accountId: string): Promise<AccountAudit> {
    return parseAccountAudit(await this.read(
      `/sim/v2/accounts/${syntheticSegment(accountId,"ACCOUNT")}/audit`));
  }

  async reconciliation(accountId: string, date: string): Promise<ReconciliationRecord> {
    return parseReconciliation(await this.read(
      `/sim/v2/reconciliation/${syntheticSegment(accountId,"ACCOUNT")}/${dateSegment(date)}`));
  }

  async dashboard(): Promise<Dashboard> {
    return parseDashboard(await this.read("/sim/v2/dashboard"));
  }

  /** There intentionally is no send(), capture(), cashout(), or fund() method. */
}

export function createReadOnlyClient(options: ClientOptions): ReadOnlySandboxClient {
  return new ReadOnlySandboxClient(options);
}
