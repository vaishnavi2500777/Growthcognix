import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/auto-refresh";
import { PageHead, Status } from "@/components/page-head";
import { apiOrLogin } from "@/lib/api";
import { RUN_LABEL, RUN_TONE, took, when } from "@/lib/format";
import type { Report, RunDetail, Step } from "@/lib/types";

export const metadata: Metadata = { title: "Research run" };

const STEP_TONE = { running: "wait", succeeded: "done", failed: "fail", skipped: "todo" } as const;
const STEP_LABEL = { running: "Working", succeeded: "Done", failed: "Failed", skipped: "Skipped" } as const;

function Cite({ ids, sources }: { ids: string[]; sources: Report["sources"] }) {
  return (
    <span className="ml-1.5 inline-flex gap-1 align-middle">
      {ids.map((id) => {
        const s = sources.find((x) => x.id === id);
        const cls = "rounded border border-line px-1 font-mono text-[10px] leading-4 text-muted";
        return s?.url
          ? <a key={id} href={s.url} target="_blank" rel="noreferrer" title={s.title} className={`${cls} hover:text-ink`}>{id}</a>
          : <span key={id} title={s?.title} className={cls}>{id}</span>;
      })}
    </span>
  );
}

function Block({ title, empty, children }: { title: string; empty: boolean; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line py-7 md:grid-cols-[200px_1fr] md:gap-10">
      <h3 className="font-medium">{title}</h3>
      <div>{empty ? <p className="text-sm text-muted">Nothing the sources could support.</p> : children}</div>
    </section>
  );
}

function Steps({ steps }: { steps: Step[] }) {
  return (
    <ol className="card divide-y divide-line">
      {steps.map((s) => (
        <li key={s.seq} className="grid grid-cols-[28px_1fr_auto] items-start gap-3 px-5 py-4">
          <span className="pt-0.5 font-mono text-xs text-muted">{String(s.seq).padStart(2, "0")}</span>
          <div>
            <p className="text-[15px]">{s.name}</p>
            {s.summary && <p className="mt-0.5 text-sm text-muted">{s.summary}</p>}
          </div>
          <Status tone={STEP_TONE[s.status]}>{STEP_LABEL[s.status]}</Status>
        </li>
      ))}
    </ol>
  );
}

function ReportView({ r }: { r: Report }) {
  const src = r.sources;
  return (
    <div className="mt-12">
      <p className="text-[20px] leading-relaxed tracking-[-0.01em]">{r.summary}</p>
      {r.limitations.map((l) => (
        <p key={l} className="mt-4 rounded-[10px] border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm">{l}</p>
      ))}
      <div className="mt-8">
        <Block title="Strengths" empty={!r.strengths.length}>
          <ul className="grid gap-2.5">{r.strengths.map((x, i) => <li key={i}>{x.point}<Cite ids={x.basis} sources={src} /></li>)}</ul>
        </Block>
        <Block title="Gaps" empty={!r.gaps.length}>
          <ul className="grid gap-2.5">{r.gaps.map((x, i) => <li key={i}>{x.point}<Cite ids={x.basis} sources={src} /></li>)}</ul>
        </Block>
        <Block title="Audiences" empty={!r.audiences.length}>
          <ul className="grid gap-5">{r.audiences.map((x, i) => (
            <li key={i}><p className="font-medium">{x.segment}<Cite ids={x.basis} sources={src} /></p>
              <p className="text-muted">{x.needs}</p><p className="mt-1 text-sm"><span className="text-muted">Reach them: </span>{x.where_to_reach}</p></li>))}</ul>
        </Block>
        <Block title="Competitors" empty={!r.competitors.length}>
          <ul className="grid gap-4">{r.competitors.map((x, i) => (
            <li key={i}><a href={x.url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-4">{x.name}</a>
              <Cite ids={x.basis} sources={src} /><p className="text-muted">{x.notes}</p></li>))}</ul>
        </Block>
        <Block title="Opportunities" empty={!r.opportunities.length}>
          <ol className="grid gap-5">{r.opportunities.map((x, i) => (
            <li key={i} className="card p-5">
              <p className="eyebrow">{x.channel}</p>
              <p className="mt-1.5 font-medium">{x.title}<Cite ids={x.basis} sources={src} /></p>
              <p className="mt-1 text-muted">{x.why}</p>
              <p className="mt-3 text-sm"><span className="font-medium">First step: </span>{x.first_step}</p>
            </li>))}</ol>
        </Block>
        <Block title="Questions for you" empty={!r.open_questions.length}>
          <ul className="grid list-disc gap-2 pl-5">{r.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
        </Block>
        <Block title="Sources" empty={!src.length}>
          <ul className="grid gap-2 text-sm">{src.map((s) => (
            <li key={s.id} className="flex gap-3"><span className="w-7 font-mono text-xs text-muted pt-0.5">{s.id}</span>
              {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="underline underline-offset-4 break-all">{s.title}</a> : <span>{s.title}</span>}</li>))}</ul>
        </Block>
      </div>
    </div>
  );
}

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await apiOrLogin<RunDetail>(`/runs/${id}`);
  const live = run.status === "queued" || run.status === "running";
  const t = took(run.started_at, run.finished_at);
  return (
    <>
      <AutoRefresh active={live} />
      <Link href="/agents" className="text-sm text-muted hover:text-ink">← Agents</Link>
      <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
        <PageHead eyebrow={`Run · ${when(run.created_at)}`} title="Market research">
          {live ? "Working through each step now. This page updates on its own."
            : [t && `Took ${t}`, run.model && `Model ${run.model}`,
               run.input_tokens + run.output_tokens > 0 && `${(run.input_tokens + run.output_tokens).toLocaleString("en-IN")} tokens`]
              .filter(Boolean).join(" · ")}
        </PageHead>
        <Status tone={RUN_TONE[run.status]}>{RUN_LABEL[run.status]}</Status>
      </div>
      <Steps steps={run.steps} />
      {run.error && <p className="mt-6 rounded-[10px] border border-danger/30 bg-danger/10 px-3 py-2.5 text-sm text-danger">{run.error.message}</p>}
      {run.output && <ReportView r={run.output} />}
    </>
  );
}
