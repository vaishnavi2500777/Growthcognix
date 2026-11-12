"use client";

import Link from "next/link";
import { useActionState } from "react";
import { login } from "@/app/actions/auth";
import { FormError, keepValues, Submit } from "@/components/form-bits";

export default function LoginPage() {
  const [state, action, pending] = useActionState(login, undefined);
  return (
    <>
      <h1 className="text-[28px] font-medium tracking-[-0.02em]">Welcome back</h1>
      <p className="mt-1 text-muted">Sign in to your GrowthCognix workspace.</p>
      <form onSubmit={keepValues(action)} className="mt-8 grid gap-4">
        <FormError message={state?.error} />
        <label className="field"><span>Work email</span>
          <input className="input" name="email" type="email" autoComplete="email" required />
        </label>
        <label className="field"><span>Password</span>
          <input className="input" name="password" type="password" autoComplete="current-password" required />
        </label>
        <Submit pending={pending} className="mt-2 w-full">Sign in</Submit>
      </form>
      <p className="mt-6 text-sm text-muted">
        New to GrowthCognix? <Link href="/signup" className="text-ink underline underline-offset-4">Create an account</Link>
      </p>
    </>
  );
}
