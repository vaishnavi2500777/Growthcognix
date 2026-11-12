import type { Metadata } from "next";
import { decideApproval } from "@/app/actions/agents";
import { PageHead, Status } from "@/components/page-head";
import { apiOrLogin } from "@/lib/api";
import { when } from "@/lib/format";
import type { Approval } from "@/lib/types";

export const metadata: Metadata = { title: "Approvals" };

export default async function Approvals() {
  const items = await apiOrLogin<Approval[]>("/approvals");
  const pending = items.filter((a) => a.status === "pending");
  const decided = items.filter((a) => a.status !== "pending");
  return (
    <>
      <PageHead eyebrow="Nothing goes out without you" title="Approvals">
        When an agent wants to publish, send or spend, the request waits here with exactly what it will do.
      </PageHead>
      {items.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="font-medium">No requests yet</p>
          <p className="mx-auto mt-1 max-w-[440px] text-sm text-muted">
            Your current agents only read and draft, so they never need approval. Requests appear here once publishing agents go live.
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {pending.map((a) => (
            <article key={a.id} className="card p-6">
              <p className="eyebrow">{a.action_type} · {when(a.created_at)}</p>
              <h2 className="mt-2 font-medium">{a.title}</h2>
              <pre className="mt-4 overflow-x-auto rounded-[10px] bg-surface-2 p-4 font-mono text-xs">{JSON.stringify(a.payload, null, 2)}</pre>
              <form action={decideApproval} className="mt-4 flex flex-wrap gap-3">
                <input type="hidden" name="id" value={a.id} />
                <button name="decision" value="approved" className="btn btn-primary">Approve</button>
                <button name="decision" value="rejected" className="btn btn-ghost">Reject</button>
              </form>
            </article>
          ))}
          {decided.length > 0 && (
            <ul className="card divide-y divide-line">
              {decided.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-4">
                  <div><p>{a.title}</p><p className="text-xs text-muted">{a.decided_at && when(a.decided_at)}</p></div>
                  <Status tone={a.status === "approved" ? "done" : "todo"}>{a.status}</Status>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
