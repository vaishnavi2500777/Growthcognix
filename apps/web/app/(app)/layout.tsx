import { redirect } from "next/navigation";
import { Suspense } from "react";
import { logout } from "@/app/actions/auth";
import { Logo } from "@/components/logo";
import { Nav } from "@/components/nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { apiOrLogin } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-dvh" aria-busy="true" />}>
      <Shell>{children}</Shell>
    </Suspense>
  );
}

async function Shell({ children }: { children: React.ReactNode }) {
  const me = await apiOrLogin<Me>("/me");
  if (!me.onboarded) redirect("/onboarding");
  const initials = me.full_name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[248px_1fr]">
      <aside className="border-b border-line px-4 py-4 md:sticky md:top-0 md:h-dvh md:border-b-0 md:border-r md:px-4 md:py-6 md:flex md:flex-col">
        <div className="flex items-center justify-between md:block">
          <Logo className="h-7" />
          <div className="md:hidden"><ThemeToggle /></div>
        </div>
        <div className="mt-4 overflow-x-auto md:mt-8"><Nav /></div>
        <div className="mt-auto hidden md:block">
          <div className="flex items-center gap-3 border-t border-line pt-4">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface-2 border border-line font-mono text-xs">{initials}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{me.full_name}</p>
              <p className="truncate text-xs text-muted">{me.organization.name}</p>
            </div>
            <ThemeToggle />
          </div>
          <form action={logout} className="mt-3">
            <button className="text-xs text-muted hover:text-ink">Sign out</button>
          </form>
        </div>
      </aside>
      <main className="px-5 py-8 sm:px-10 md:py-12">
        <div className="mx-auto max-w-[1040px]">{children}</div>
      </main>
    </div>
  );
}
