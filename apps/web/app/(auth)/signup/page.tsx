"use client";

import Link from "next/link";
import { useActionState } from "react";
import { signup } from "@/app/actions/auth";
import { FieldError, FormError, keepValues, Submit } from "@/components/form-bits";

export default function SignupPage() {
  const [state, action, pending] = useActionState(signup, undefined);
  const f = state?.fields ?? {};
  return (
    <>
      <h1 className="text-[28px] font-medium tracking-[-0.02em]">Create your workspace</h1>
      <p className="mt-1 text-muted">Set up your business in a few steps.</p>
      <form onSubmit={keepValues(action)} className="mt-8 grid gap-4">
        <FormError message={state?.error} />
        <label className="field"><span>Your name</span>
          <input className="input" name="full_name" autoComplete="name" required minLength={2} />
          <FieldError message={f.full_name} />
        </label>
        <label className="field"><span>Business name</span>
          <input className="input" name="organization_name" autoComplete="organization" required minLength={2} />
          <FieldError message={f.organization_name} />
        </label>
        <label className="field"><span>Work email</span>
          <input className="input" name="email" type="email" autoComplete="email" required />
          <FieldError message={f.email} />
        </label>
        <label className="field"><span>Password</span>
          <input className="input" name="password" type="password" autoComplete="new-password" required minLength={10} />
          <small>At least 10 characters.</small>
          <FieldError message={f.password} />
        </label>
        <Submit pending={pending} className="mt-2 w-full">Create account</Submit>
      </form>
      <p className="mt-6 text-sm text-muted">
        Already have an account? <Link href="/login" className="text-ink underline underline-offset-4">Sign in</Link>
      </p>
    </>
  );
}
