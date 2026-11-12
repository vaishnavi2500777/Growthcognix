"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { FormState, Run } from "@/lib/types";

export async function startRun(_: FormState, form: FormData): Promise<FormState> {
  let run: Run;
  try {
    run = await api<Run>(`/agents/${form.get("slug")}/runs`, { method: "POST" });
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401) redirect("/logout");
      return { error: e.body.error.message };
    }
    return { error: "We couldn't start the agent. Please try again." };
  }
  redirect(`/runs/${run.id}`);
}

export async function decideApproval(form: FormData) {
  await api(`/approvals/${form.get("id")}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision: form.get("decision"), note: form.get("note") || null }),
  });
  revalidatePath("/approvals");
}
