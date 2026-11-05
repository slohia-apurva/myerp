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

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as { detail?: string };
  if (!res.ok) throw new ApiError(data.detail ?? `Something went wrong (HTTP ${res.status}).`, res.status);
  return data as T;
}

export type Session =
  | { signed_in: false; google_client_id: string }
  | { signed_in: true; user: { email: string; name: string } };
