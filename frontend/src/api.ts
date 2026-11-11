// Small JSON client for the MyERP API. Sends the CSRF token Django sets in
// the "csrftoken" cookie (GET /api/auth/session/ makes sure it exists).

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
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
    const parts = Object.values(record).flatMap((v) => (Array.isArray(v) ? v : [v]));
    const text = parts.filter((p) => typeof p === "string").join(" ");
    if (text) return text;
  }
  return `Something went wrong (HTTP ${status}).`;
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
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status);
  return data as T;
}

export type SignedIn = {
  signed_in: true;
  user: { email: string; name: string; is_owner: boolean; is_platform_admin?: boolean };
  permissions: string[];
};

export type Session = { signed_in: false; google_client_id: string } | SignedIn;
