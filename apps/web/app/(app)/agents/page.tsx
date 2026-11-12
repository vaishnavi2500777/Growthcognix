import type { Metadata } from "next";
import { PageHead, Status } from "@/components/page-head";

export const metadata: Metadata = { title: "Agents" };

export default function Agents() {
  return (
    <>
      <PageHead eyebrow="Your marketing team" title="Agents">
        Agents go live one at a time, each tested before it can act for you. Anything that publishes, sends or spends will always ask first.
      </PageHead>
      <article className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-[560px]">
            <p className="eyebrow">Research</p>
            <h2 className="mt-2 text-[20px] font-medium">Market Research Agent</h2>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">
              Reads your business profile, studies your market and competitors, and writes up opportunities you can act on.
              It only reads and drafts, so it never needs your approval to run.
            </p>
          </div>
          <Status tone="wait">Not active yet</Status>
        </div>
        <div className="mt-6 border-t border-line pt-5 text-sm text-muted">
          Needs an AI provider connection, which arrives in the next release.
        </div>
      </article>
    </>
  );
}
