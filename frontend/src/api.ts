// Small JSON client for the MyERP API. Sends the CSRF token Django sets in
// the "csrftoken" cookie (GET /api/auth/session/ makes sure it exists).

/** The record a duplicate clashed with (core/duplicates.py on the server). */
export type Existing = { kind: string; id: string; name: string; company?: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly existing?: Existing,
  ) {
    super(message);
  }
}

function existingOf(data: unknown): Existing | undefined {
  if (data && typeof data === "object" && "existing" in data) {
    const e = (data as { existing: unknown }).existing;
    if (e && typeof e === "object" && "kind" in e && "id" in e) return e as Existing;
  }
  return undefined;
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

// DRF errors come as {"detail": "..."} or {"field": ["...", ...]}.
function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    const text = flatten(Object.entries(record).filter(([k]) => k !== "existing").map(([, v]) => v)).join(" ");
    if (text) return text;
  }
  return `Something went wrong (HTTP ${status}).`;
}

function flatten(values: unknown[]): string[] {
  return values.flatMap((v) =>
    typeof v === "string" ? [v] : Array.isArray(v) ? flatten(v) : v && typeof v === "object" ? flatten(Object.values(v)) : [],
  );
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

export async function api<T>(path: string, body?: unknown, method?: Method): Promise<T> {
  const verb: Method = method ?? (body === undefined ? "GET" : "POST");
  const res = await fetch(`/api/${path}`, {
    method: verb,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(verb === "GET" ? {} : { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data: unknown = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, existingOf(data));
  return data as T;
}

export type SignedIn = {
  signed_in: true;
  user: { email: string; name: string; is_owner: boolean; is_platform_admin?: boolean };
  permissions: string[];
};

export type Session = { signed_in: false; google_client_id: string } | SignedIn;

/** POST a form with a file (multipart); errors as for `api`. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
    body: form,
  });
  const data: unknown = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, existingOf(data));
  return data as T;
}
