import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { BusinessForm } from "@/components/business-form";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { api, apiOrLogin } from "@/lib/api";
import type { Industry, Me } from "@/lib/types";

export const metadata: Metadata = { title: "Set up your business" };

export default function OnboardingPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh" aria-busy="true" />}>
      <Onboarding />
    </Suspense>
  );
}

async function Onboarding() {
  const me = await apiOrLogin<Me>("/me");
  if (me.onboarded) redirect("/dashboard");
  const industries = await api<Industry[]>("/industries", { auth: false });
  return (
    <div className="mx-auto max-w-[960px] px-6 sm:px-10">
      <header className="flex items-center justify-between py-6">
        <Logo />
        <ThemeToggle />
      </header>
      <div className="pt-8 pb-10">
        <p className="eyebrow">Step 1 of 1 · Business profile</p>
        <h1 className="mt-3 text-[34px] leading-tight tracking-[-0.02em] font-medium">
          Tell us about <span className="font-serif italic text-primary">{me.organization.name}</span>
        </h1>
        <p className="mt-2 max-w-[560px] text-muted">
          Your agents start from this profile. Be specific; you can change it any time.
        </p>
      </div>
      <BusinessForm industries={industries} defaultCompany={me.organization.name} next="/dashboard" submitLabel="Save and continue" />
    </div>
  );
}
