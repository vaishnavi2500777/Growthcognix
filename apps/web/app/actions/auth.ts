"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { api, ApiError, SESSION_COOKIE } from "@/lib/api";
import type { FormState } from "@/lib/types";

async function startSession(token: string) {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax",
    path: "/", maxAge: 60 * 60 * 12,
  });
}

function fieldErrors(e: ApiError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of e.body.error.details?.fields ?? []) out[String(f.loc.at(-1))] = f.msg;
  return out;
}

export async function signup(_: FormState, form: FormData): Promise<FormState> {
  try {
    const { access_token } = await api<{ access_token: string }>("/auth/register", {
      method: "POST", auth: false,
      body: JSON.stringify({
        full_name: form.get("full_name"), email: form.get("email"),
        password: form.get("password"), organization_name: form.get("organization_name"),
      }),
    });
    await startSession(access_token);
  } catch (e) {
    if (e instanceof ApiError) return { error: e.body.error.message, fields: fieldErrors(e) };
    return { error: "We couldn't reach GrowthCognix. Please try again." };
  }
  redirect("/onboarding");
}

export async function login(_: FormState, form: FormData): Promise<FormState> {
  try {
    const { access_token } = await api<{ access_token: string }>("/auth/login", {
      method: "POST", auth: false,
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    await startSession(access_token);
  } catch (e) {
    if (e instanceof ApiError) return { error: e.body.error.message };
    return { error: "We couldn't reach GrowthCognix. Please try again." };
  }
  redirect("/dashboard");
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
