"use client";

import { useActionState } from "react";
import { startRun } from "@/app/actions/agents";
import { FormError, keepValues, Submit } from "@/components/form-bits";

export function RunButton({ slug, disabled, label }: { slug: string; disabled?: boolean; label: string }) {
  const [state, action, pending] = useActionState(startRun, undefined);
  return (
    <form onSubmit={keepValues(action)} className="grid gap-3">
      <input type="hidden" name="slug" value={slug} />
      <FormError message={state?.error} />
      <Submit pending={pending} className={disabled ? "pointer-events-none opacity-50" : ""}>{label}</Submit>
    </form>
  );
}
