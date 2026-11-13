import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/auto-refresh";
import { PageHead, Status } from "@/components/page-head";
import { apiOrLogin } from "@/lib/api";
import { RUN_LABEL, RUN_TONE, took, when } from "@/lib/format";
import type { CompetitorReport, PersonaReport, Report, RunDetail, Source, Step } from "@/lib/types";

export const metadata: Metadata = { title: "Agent run" };

const TITLE: Record<string, string> = {
  "market-research": "Market research",
  "competitor-analysis": "Competitor analysis",
  "customer-persona": "Customer personas",
};

const STEP_TONE = { running: "wait", succeeded: "done", failed: "fail", skipped: "todo" } as const;
const STEP_LABEL = { running: "Working", succeeded: "Done", failed: "Failed", skipped: "Skipped" } as const;

function SourceLink({ s, className, children }: { s: Source; className: string; children: React.ReactNode }) {
  if (!s.url) return <span title={s.title} className={className}>{children}</span>;
  // R points at an earlier run inside the app; everything else is an outside page.
  return s.url.startsWith("/")
    ? <Link href={s.url} title={s.title} className={className}>{children}</Link>
    : <a href={s.url} target="_blank" rel="noreferrer" title={s.title} className={className}>{children}</a>;
}

function Cite({ ids, sources }: { ids: string[]; sources: Source[] }) {
  return (
    <span className="ml-1.5 inline-flex gap-1 align-middle">
      {ids.map((id) => {
        const s = sources.find((x) => x.id === id);
        const cls = "rounded border border-line px-1 font-mono text-[10px] leading-4 text-muted";
        return s
          ? <SourceLink key={id} s={s} className={s.url ? `${cls} hover:text-ink` : cls}>{id}</SourceLink>
          : <span key={id} className={cls}>{id}</span>;
      })}
    </span>
  );
}

function Block({ title, empty, emptyText, children }: {
  title: string; empty: boolean; emptyText?: string; children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 border-t border-line py-7 md:grid-cols-[200px_1fr] md:gap-10">
      <h3 className="font-medium">{title}</h3>
      <div>{empty ? <p className="text-sm text-muted">{emptyText ?? "Nothing the sources could support."}</p> : children}</div>
    </section>
  );
}

function Lead({ r }: { r: { summary: string; limitations: string[] } }) {
  return (
    <>
      <p className="text-[20px] leading-relaxed tracking-[-0.01em]">{r.summary}</p>
      {r.limitations.map((l) => (
        <p key={l} className="mt-4 rounded-[10px] border border-warning/30 bg-warning/10 px-3 py-2.5 text-sm">{l}</p>
      ))}
    </>
  );
}

function Questions({ items }: { items: string[] }) {
  return (
    <Block title="Questions for you" empty={!items.length}>
      <ul className="grid list-disc gap-2 pl-5">{items.map((q) => <li key={q}>{q}</li>)}</ul>
    </Block>
  );
}

function Sources({ src }: { src: Source[] }) {
  return (
    <Block title="Sources" empty={!src.length}>
      <ul className="grid gap-2 text-sm">{src.map((s) => (
        <li key={s.id} className="flex gap-3"><span className="w-7 font-mono text-xs text-muted pt-0.5">{s.id}</span>
          <SourceLink s={s} className={s.url ? "underline underline-offset-4 break-all" : ""}>{s.title}</SourceLink></li>))}</ul>
    </Block>
  );
}

function Field({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1"><ul className="grid gap-1">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></dd>
    </div>
  );
}

function CompetitorView({ r }: { r: CompetitorReport }) {
  const src = r.sources;
  return (
    <div className="mt-12">
      <Lead r={r} />
      <div className="mt-8">
        <Block title="Competitors" empty={!r.competitors.length}
          emptyText="No competitors listed. Only businesses found in a real source are shown, and this run had none.">
          <ul className="grid gap-5">{r.competitors.map((x, i) => (
            <li key={i} className="card p-5">
              <a href={x.url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-4">{x.name}</a>
              <Cite ids={x.basis} sources={src} />
              {x.what_they_sell && <p className="mt-1.5">{x.what_they_sell}</p>}
              {x.positioning && <p className="mt-1 text-muted">{x.positioning}</p>}
              {x.pricing_signals && (
                <p className="mt-3 text-sm"><span className="font-medium">Prices they state: </span>{x.pricing_signals}</p>
              )}
              {(x.strengths.length > 0 || x.weaknesses.length > 0) && (
                <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                  <Field label="Strengths" items={x.strengths} />
                  <Field label="Weaknesses" items={x.weaknesses} />
                </dl>
              )}
            </li>))}</ul>
        </Block>
        <Block title="How you compare" empty={!r.comparison.length}>
          <ul className="card divide-y divide-line">{r.comparison.map((x, i) => (
            <li key={i} className="grid gap-2 px-5 py-4 text-[15px] md:grid-cols-[160px_1fr_1fr] md:gap-6">
              <p className="font-medium">{x.dimension}<Cite ids={x.basis} sources={src} /></p>
              <p><span className="block text-xs text-muted">You</span>{x.this_business}</p>
              <p><span className="block text-xs text-muted">Competitors</span>{x.competitors}</p>
            </li>))}</ul>
        </Block>
        <Block title="Where you can stand apart" empty={!r.differentiation.length}>
          <ol className="grid gap-5">{r.differentiation.map((x, i) => (
            <li key={i} className="card p-5">
              <p className="font-medium">{x.title}<Cite ids={x.basis} sources={src} /></p>
              <p className="mt-1 text-muted">{x.why}</p>
              <p className="mt-3 text-sm"><span className="font-medium">First step: </span>{x.first_step}</p>
            </li>))}</ol>
        </Block>
        <Questions items={r.open_questions} />
        <Sources src={src} />
      </div>
    </div>
  );
}

function PersonaView({ r }: { r: PersonaReport }) {
  const src = r.sources;
  return (
    <div className="mt-12">
      <Lead r={r} />
      <div className="mt-8">
        <Block title="Personas" empty={!r.personas.length}
          emptyText="No personas. None could be tied to your profile, website or research.">
          <ul className="grid gap-5">{r.personas.map((x, i) => (
            <li key={i} className="card p-5">
              {x.segment && <p className="eyebrow">{x.segment}</p>}
              <p className="mt-1.5 text-[17px] font-medium">{x.name}<Cite ids={x.basis} sources={src} /></p>
              {x.role && <p className="mt-1 text-muted">{x.role}</p>}
              <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                <Field label="Goals" items={x.goals} />
                <Field label="Pains" items={x.pains} />
                <Field label="What makes them buy" items={x.buying_triggers} />
                <Field label="What holds them back" items={x.objections} />
                <Field label="Where to reach them" items={x.channels} />
                <Field label="Languages" items={x.languages} />
              </dl>
              {x.message && (
                <p className="mt-4 border-t border-line pt-4 text-[15px]"><span className="font-medium">What to say: </span>{x.message}</p>
              )}
            </li>))}</ul>
        </Block>
        <Questions items={r.open_questions} />
        <Sources src={src} />
      </div>
    </div>
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
      <Lead r={r} />
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
        <Questions items={r.open_questions} />
        <Sources src={src} />
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
        <PageHead eyebrow={`Run · ${when(run.created_at)}`} title={TITLE[run.agent_slug] ?? "Agent run"}>
          {live ? "Working through each step now. This page updates on its own."
            : [t && `Took ${t}`, run.model && `Model ${run.model}`,
               run.input_tokens + run.output_tokens > 0 && `${(run.input_tokens + run.output_tokens).toLocaleString("en-IN")} tokens`]
              .filter(Boolean).join(" · ")}
        </PageHead>
        <Status tone={RUN_TONE[run.status]}>{RUN_LABEL[run.status]}</Status>
      </div>
      <Steps steps={run.steps} />
      {run.error && <p className="mt-6 rounded-[10px] border border-danger/30 bg-danger/10 px-3 py-2.5 text-sm text-danger">{run.error.message}</p>}
      {run.output && (run.agent_slug === "competitor-analysis"
        ? <CompetitorView r={run.output as CompetitorReport} />
        : run.agent_slug === "customer-persona"
          ? <PersonaView r={run.output as PersonaReport} />
          : <ReportView r={run.output as Report} />)}
    </>
  );
}
