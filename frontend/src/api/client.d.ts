/** Type declarations for the (untyped) shared fetch wrapper `client.js`. */
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string);
}

export function setTokens(access: string | null, refresh: string | null): void;
export function setSessionId(sid: string | null): void;
export function getAccessToken(): string;
export function getRefreshToken(): string;
export function getSessionId(): string;
export function getTokens(): { accessToken: string; refreshToken: string; sessionId: string };
export function tryRefresh(): Promise<boolean>;

interface ApiCallOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  raw?: boolean;
}

export const api: {
  get: <T = any>(p: string, o?: Omit<ApiCallOptions, "method">) => Promise<T>;
  post: <T = any>(p: string, body?: unknown, o?: Omit<ApiCallOptions, "method">) => Promise<T>;
  put: <T = any>(p: string, body?: unknown, o?: Omit<ApiCallOptions, "method">) => Promise<T>;
  patch: <T = any>(p: string, body?: unknown, o?: Omit<ApiCallOptions, "method">) => Promise<T>;
  del: <T = any>(p: string, o?: Omit<ApiCallOptions, "method">) => Promise<T>;
};

export function wsUrl(jobId: string): string;
export function downloadBlob(blob: Blob, filename: string): void;
export function downloadFile(path: string, filename: string): Promise<void>;
export function formatNumber(n: number | null | undefined, digits?: number): string;
export function formatPct(n: number | null | undefined): string;
export function formatDate(iso?: string, withTime?: boolean): string;
export function timeAgo(iso?: string): string;
export function prettyOp(op?: string): string;