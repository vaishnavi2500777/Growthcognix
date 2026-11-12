export type Industry = { id: string; slug: string; name: string; subcategories: Industry[] };
export type Offering = { id?: string; kind: "product" | "service"; name: string; description?: string | null };
export type Me = {
  id: string; email: string; full_name: string; role: string; onboarded: boolean;
  organization: { id: string; name: string; slug: string; country_code: string; timezone: string };
};
export type BusinessProfile = {
  company_name: string; website: string | null; industry: Industry; parent_industry: Industry;
  business_model: "b2b" | "b2c" | "both"; description: string; target_customers: string;
  locations: string[]; languages: string[]; offerings: Offering[];
};
export type FormState = { error?: string; fields?: Record<string, string> } | undefined;

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type Run = {
  id: string; agent_slug: string; status: RunStatus; model: string | null;
  input_tokens: number; output_tokens: number; created_at: string;
  started_at: string | null; finished_at: string | null; error: { message: string } | null;
};
export type Step = {
  seq: number; name: string; kind: string; status: "running" | "succeeded" | "failed" | "skipped";
  summary: string | null; started_at: string; finished_at: string | null;
};
type Basis = { basis: string[] };
export type Report = {
  summary: string;
  strengths: ({ point: string } & Basis)[];
  gaps: ({ point: string } & Basis)[];
  audiences: ({ segment: string; needs: string; where_to_reach: string } & Basis)[];
  competitors: ({ name: string; url: string; notes: string } & Basis)[];
  opportunities: ({ title: string; why: string; first_step: string; channel: string } & Basis)[];
  open_questions: string[];
  sources: { id: string; kind: string; title: string; url: string | null }[];
  limitations: string[];
};
export type RunDetail = Run & { output: Report | null; steps: Step[] };
export type Agent = {
  slug: string; code: string; name: string; level: number; department: string;
  description: string; risk: string; version: string; can_run: boolean;
  blocked_reason: string | null; last_run: Run | null;
};
export type Approval = {
  id: string; action_type: string; title: string; payload: Record<string, unknown>;
  risk: string; status: "pending" | "approved" | "rejected" | "expired" | "executed";
  requested_by_agent: string | null; run_id: string | null; decided_at: string | null;
  decision_note: string | null; created_at: string;
};
