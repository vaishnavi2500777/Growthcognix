import type { Metadata } from "next";
import Link from "next/link";
import { PageHead, Status } from "@/components/page-head";
import { RunButton } from "@/components/run-button";
import { apiOrLogin } from "@/lib/api";
import { RUN_LABEL, RUN_TONE, took, when } from "@/lib/format";
import type { Agent, Run } from "@/lib/types";

export const metadata: Metadata = { title: "Agents" };

const RISK = { read: "Reads only", draft: "Drafts for review", external: "Acts only with approval" };

export default async function Agents() {
  const [agents, runs] = await Promise.all([apiOrLogin<Agent[]>("/agents"), apiOrLogin<Run[]>("/runs?limit=20")]);
  const names = Object.fromEntries(agents.map((a) => [a.slug, a.name]));
  return (
    <>
      <PageHead eyebrow="Your marketing team" title="Agents">
        Agents go live one at a time. Anything that publishes, sends or spends will always ask you first.
      </PageHead>

      <div className="grid gap-4">
        {agents.map((a) => (
          <article key={a.slug} className="card p-6">
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="max-w-[580px]">
                <p className="eyebrow">{a.code} · {a.department} · {RISK[a.risk as keyof typeof RISK]}</p>
                <h2 className="mt-2 text-[20px] font-medium">{a.name}</h2>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">{a.description}</p>
                {a.last_run && (
                  <p className="mt-4 text-sm text-muted">
                    Last run {when(a.last_run.created_at)} ·{" "}
                    <Link href={`/runs/${a.last_run.id}`} className="text-ink underline underline-offset-4">
                      {RUN_LABEL[a.last_run.status].toLowerCase()}
                    </Link>
                  </p>
                )}
              </div>
              <div className="w-full sm:w-auto">
                {a.can_run
                  ? <RunButton slug={a.slug} label={a.last_run ? "Run again" : "Run research"} />
                  : <Status tone="wait">{a.blocked_reason}</Status>}
              </div>
            </div>
          </article>
        ))}
      </div>

      <section className="mt-12">
        <h2 className="font-medium">Run history</h2>
        {runs.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No runs yet. Each run, its steps and its sources will be listed here.</p>
        ) : (
          <ul className="card mt-4 divide-y divide-line">
            {runs.map((r) => (
              <li key={r.id}>
                <Link href={`/runs/${r.id}`} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 hover:bg-surface-2">
                  <div>
                    <p className="text-[15px]">{names[r.agent_slug] ?? r.agent_slug}</p>
                    <p className="text-xs text-muted">
                      {when(r.created_at)}{took(r.started_at, r.finished_at) && ` · took ${took(r.started_at, r.finished_at)}`}
                    </p>
                  </div>
                  <Status tone={RUN_TONE[r.status]}>{RUN_LABEL[r.status]}</Status>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
