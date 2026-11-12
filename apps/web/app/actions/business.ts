"use server";

import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { FormState, Offering } from "@/lib/types";

const list = (v: FormDataEntryValue | null) =>
  String(v ?? "").split(",").map((s) => s.trim()).filter(Boolean);

export async function saveBusinessProfile(_: FormState, form: FormData): Promise<FormState> {
  let offerings: Offering[] = [];
  try {
    offerings = JSON.parse(String(form.get("offerings") ?? "[]"));
  } catch {
    return { error: "Add at least one product or service." };
  }
  const website = String(form.get("website") ?? "").trim();
  try {
    await api("/business-profile", {
      method: "PUT",
      body: JSON.stringify({
        company_name: form.get("company_name"),
        website: website ? (website.startsWith("http") ? website : `https://${website}`) : null,
        industry_id: form.get("industry_id") || null,
        business_model: form.get("business_model"),
        description: form.get("description"),
        target_customers: form.get("target_customers"),
        locations: list(form.get("locations")),
        languages: list(form.get("languages")),
        offerings: offerings.filter((o) => o.name.trim()),
      }),
    });
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401) redirect("/login");
      const fields: Record<string, string> = {};
      for (const f of e.body.error.details?.fields ?? []) fields[String(f.loc[0])] = f.msg;
      return { error: e.body.error.message, fields };
    }
    return { error: "We couldn't save your profile. Please try again." };
  }
  redirect(String(form.get("next") || "/dashboard"));
}
