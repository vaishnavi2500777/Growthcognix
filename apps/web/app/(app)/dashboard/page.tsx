import type { Metadata } from "next";
import Link from "next/link";
import { PageHead, Status } from "@/components/page-head";
import { apiOrLogin } from "@/lib/api";
import type { BusinessProfile, Me } from "@/lib/types";

export const metadata: Metadata = { title: "Overview" };

function greeting(tz: string) {
  const h = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hourCycle: "h23", timeZone: tz }).format(new Date()));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default async function Dashboard() {
  const [me, p] = await Promise.all([apiOrLogin<Me>("/me"), apiOrLogin<BusinessProfile>("/business-profile")]);
  const steps = [
    { label: "Create your workspace", done: true },
    { label: "Describe your business", done: me.onboarded, href: "/business" },
    { label: "Switch on your first agent", done: false, note: "Market Research Agent" },
    { label: "Connect your marketing accounts", done: false, note: "Website, social and ads" },
  ];
  const done = steps.filter((s) => s.done).length;
  return (
    <>
      <PageHead eyebrow={me.organization.name} title={`${greeting(me.organization.timezone)}, ${me.full_name.split(" ")[0]}.`}>
        This is your marketing command centre. It fills with real work as your agents go live.
      </PageHead>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <section className="card p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Getting started</h2>
            <span className="font-mono text-xs text-muted">{done} of {steps.length}</span>
          </div>
          <div className="mt-4 h-1 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full bg-primary" style={{ width: `${(done / steps.length) * 100}%` }} />
          </div>
          <ul className="mt-6 divide-y divide-line">
            {steps.map((s) => (
              <li key={s.label} className="flex items-center justify-between gap-4 py-3.5">
                <div className="flex items-center gap-3">
                  <span className={`grid h-5 w-5 place-items-center rounded-full border ${s.done ? "border-primary bg-primary text-primary-fg" : "border-line"}`}>
                    {s.done && <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="m2.5 6.2 2.3 2.3 4.7-5" /></svg>}
                  </span>
                  <div>
                    <p className={`text-[15px] ${s.done ? "text-muted line-through decoration-line" : ""}`}>{s.label}</p>
                    {s.note && <p className="text-xs text-muted">{s.note}</p>}
                  </div>
                </div>
                {s.done ? <Status tone="done">Done</Status> : <Status tone="todo">Up next</Status>}
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Your business</h2>
            <Link href="/business" className="text-sm text-muted hover:text-ink">Edit</Link>
          </div>
          <p className="mt-4 text-[20px] font-medium tracking-[-0.01em]">{p.company_name}</p>
          <p className="text-sm text-muted">{p.parent_industry.name} · {p.industry.name} · {p.business_model.toUpperCase()}</p>
          <p className="mt-4 line-clamp-4 text-[15px] leading-relaxed">{p.description}</p>
          <dl className="mt-6 grid gap-4 border-t border-line pt-5 text-sm">
            <div><dt className="eyebrow">Offerings</dt>
              <dd className="mt-1.5 flex flex-wrap gap-1.5">{p.offerings.map((o) => (
                <span key={o.id} className="rounded-md border border-line px-2 py-0.5">{o.name}</span>))}</dd></div>
            {p.locations.length > 0 && <div><dt className="eyebrow">Markets</dt><dd className="mt-1.5">{p.locations.join(", ")}</dd></div>}
          </dl>
        </section>
      </div>

      <section className="card mt-6 flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="font-medium">Agent activity</h2>
          <p className="mt-1 text-sm text-muted">No agent has run yet. When one does, every step and approval appears here.</p>
        </div>
        <Link href="/agents" className="btn btn-ghost">View agents</Link>
      </section>
    </>
  );
}
