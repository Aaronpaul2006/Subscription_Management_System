// Thin fetch wrapper: session cookie + CSRF header, JSON in/out, typed errors.

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, unknown>;

  constructor(status: number, code: string, message: string, fields: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  fieldError(name: string): string | undefined {
    const value = this.fields?.[name];
    if (!value) return undefined;
    if (Array.isArray(value)) return String(value[0]);
    return String(value);
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];
}

let lastTiming = "";
const timingListeners = new Set<(t: string) => void>();
export function onServerTiming(fn: (t: string) => void) {
  timingListeners.add(fn);
  fn(lastTiming);
  return () => void timingListeners.delete(fn);
}

export async function ensureCsrf() {
  if (!cookie("csrftoken")) await fetch("/api/auth/csrf/", { credentials: "same-origin" });
}

type Query = Record<string, string | number | boolean | undefined | null | string[]>;

export function qs(params: Query = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; query?: Query } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    await ensureCsrf();
    headers["X-CSRFToken"] = decodeURIComponent(cookie("csrftoken") ?? "");
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`/api/${path}${qs(options.query)}`, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const timing = response.headers.get("X-Response-Time");
  if (timing) {
    lastTiming = `${method} /api/${path.split("?")[0]} · ${timing}`;
    timingListeners.forEach((fn) => fn(lastTiming));
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!response.ok) {
    const err = data?.error ?? {};
    throw new ApiError(
      response.status,
      err.code ?? "error",
      err.message ?? `Request failed (${response.status})`,
      err.fields ?? {},
    );
  }
  return data as T;
}

export const get = <T>(path: string, query?: Query) => api<T>(path, { query });
export const post = <T>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", body });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
