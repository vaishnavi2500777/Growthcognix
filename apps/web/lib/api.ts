import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export const SESSION_COOKIE = "gc_session";
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type ApiErrorBody = {
  error: { code: string; message: string; details?: { fields?: { loc: (string | number)[]; msg: string }[] } };
};

export class ApiError extends Error {
  constructor(public status: number, public body: ApiErrorBody) {
    super(body.error.message);
  }
}

/** Server-side call to the GrowthCognix API. The token never reaches the browser. */
export async function api<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (init.auth !== false) {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (token) headers.set("authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({
      error: { code: "NETWORK", message: "The service is unavailable. Please try again." },
    }))) as ApiErrorBody;
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

/** For pages: send the visitor to sign in when the session is missing or expired. */
export async function apiOrLogin<T>(path: string): Promise<T> {
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/logout");
    throw e;
  }
}
