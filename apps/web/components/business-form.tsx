"use client";

import { useActionState, useMemo, useState } from "react";
import { saveBusinessProfile } from "@/app/actions/business";
import { FieldError, FormError, keepValues, Submit } from "@/components/form-bits";
import type { BusinessProfile, Industry, Offering } from "@/lib/types";

const MODELS = [
  { v: "b2b", label: "B2B", hint: "You sell to businesses" },
  { v: "b2c", label: "B2C", hint: "You sell to consumers" },
  { v: "both", label: "Both", hint: "Businesses and consumers" },
] as const;

function Section({ n, title, hint, children }: { n: string; title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-6 border-t border-line py-8 md:grid-cols-[240px_1fr] md:gap-10">
      <div>
        <p className="font-mono text-xs text-muted">{n}</p>
        <h2 className="mt-1 text-[17px] font-medium">{title}</h2>
        <p className="mt-1 text-sm text-muted">{hint}</p>
      </div>
      <div className="grid gap-5">{children}</div>
    </section>
  );
}

export function BusinessForm({ industries, initial, next, submitLabel, defaultCompany }: {
  industries: Industry[]; initial?: BusinessProfile | null; next: string; submitLabel: string;
  defaultCompany?: string;
}) {
  const [state, action, pending] = useActionState(saveBusinessProfile, undefined);
  const f = state?.fields ?? {};
  const [groupId, setGroupId] = useState(initial?.parent_industry.id ?? "");
  const [subId, setSubId] = useState(initial?.industry.id ?? "");
  const [model, setModel] = useState<string>(initial?.business_model ?? "");
  const [offerings, setOfferings] = useState<Offering[]>(
    initial?.offerings.length ? initial.offerings : [{ kind: "product", name: "", description: "" }],
  );
  const subs = useMemo(() => industries.find((g) => g.id === groupId)?.subcategories ?? [], [industries, groupId]);
  const update = (i: number, patch: Partial<Offering>) =>
    setOfferings((o) => o.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  return (
    <form onSubmit={keepValues(action)} className="pb-24">
      <input type="hidden" name="next" value={next} />
      <input type="hidden" name="offerings" value={JSON.stringify(offerings)} />
      <input type="hidden" name="business_model" value={model} />
      <FormError message={state?.error} />

      <Section n="01" title="Company" hint="How customers know you.">
        <label className="field"><span>Business name</span>
          <input className="input" name="company_name" defaultValue={initial?.company_name ?? defaultCompany} required minLength={2} />
          <FieldError message={f.company_name} />
        </label>
        <label className="field"><span>Website <span className="text-muted font-normal">(optional)</span></span>
          <input className="input" name="website" inputMode="url" placeholder="yourbusiness.in" defaultValue={initial?.website ?? ""} />
          <FieldError message={f.website} />
        </label>
      </Section>

      <Section n="02" title="Industry" hint="Agents use your industry's playbook, channels and rules.">
        <div className="grid gap-5 sm:grid-cols-2">
          <label className="field"><span>Industry</span>
            <select className="input" value={groupId} required
              onChange={(e) => { setGroupId(e.target.value); setSubId(""); }}>
              <option value="" disabled>Select an industry</option>
              {industries.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Category</span>
            <select className="input" name="industry_id" value={subId} required disabled={!groupId}
              onChange={(e) => setSubId(e.target.value)}>
              <option value="" disabled>{groupId ? "Select a category" : "Choose an industry first"}</option>
              {subs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <FieldError message={f.industry_id} />
          </label>
        </div>
        <fieldset className="field">
          <span>Who do you sell to?</span>
          <div className="grid gap-2 sm:grid-cols-3">
            {MODELS.map((m) => (
              <button type="button" key={m.v} onClick={() => setModel(m.v)} aria-pressed={model === m.v}
                className={`rounded-[10px] border px-4 py-3 text-left transition ${model === m.v
                  ? "border-primary bg-surface ring-2 ring-[var(--gc-ring)]" : "border-line bg-surface hover:bg-surface-2"}`}>
                <span className="block text-[15px] font-medium">{m.label}</span>
                <span className="block text-xs text-muted">{m.hint}</span>
              </button>
            ))}
          </div>
          <FieldError message={f.business_model} />
        </fieldset>
      </Section>

      <Section n="03" title="What you do" hint="In your own words. This is what every agent reads first.">
        <label className="field"><span>Describe your business</span>
          <textarea className="input" name="description" rows={4} required minLength={20} defaultValue={initial?.description}
            placeholder="What you make or offer, what makes you different, and how long you've been doing it." />
          <FieldError message={f.description} />
        </label>
        <label className="field"><span>Your ideal customers</span>
          <textarea className="input" name="target_customers" rows={3} required minLength={5} defaultValue={initial?.target_customers}
            placeholder="Who buys from you, where they are, and what they care about." />
          <FieldError message={f.target_customers} />
        </label>
      </Section>

      <Section n="04" title="Products and services" hint="Add each one you want to market.">
        <ul className="grid gap-3">
          {offerings.map((o, i) => (
            <li key={i} className="card grid gap-3 p-4 sm:grid-cols-[120px_1fr_auto] sm:items-start">
              <select className="input" value={o.kind} aria-label="Type"
                onChange={(e) => update(i, { kind: e.target.value as Offering["kind"] })}>
                <option value="product">Product</option>
                <option value="service">Service</option>
              </select>
              <div className="grid gap-2">
                <input className="input" placeholder="Name" value={o.name} aria-label="Name"
                  onChange={(e) => update(i, { name: e.target.value })} />
                <input className="input" placeholder="Short description (optional)" value={o.description ?? ""}
                  aria-label="Description" onChange={(e) => update(i, { description: e.target.value })} />
              </div>
              <button type="button" className="btn btn-ghost h-11 px-3 text-sm" disabled={offerings.length === 1}
                onClick={() => setOfferings((x) => x.filter((_, j) => j !== i))}>Remove</button>
            </li>
          ))}
        </ul>
        <button type="button" className="btn btn-ghost w-fit"
          onClick={() => setOfferings((x) => [...x, { kind: "product", name: "", description: "" }])}>
          + Add another
        </button>
        <FieldError message={f.offerings} />
      </Section>

      <Section n="05" title="Markets" hint="Separate with commas.">
        <label className="field"><span>Where you sell</span>
          <input className="input" name="locations" placeholder="Bengaluru, Mysuru, Karnataka" defaultValue={initial?.locations.join(", ")} />
        </label>
        <label className="field"><span>Languages your customers use</span>
          <input className="input" name="languages" placeholder="English, Kannada, Hindi" defaultValue={initial?.languages.join(", ")} />
        </label>
      </Section>

      <div className="sticky bottom-0 -mx-6 flex items-center justify-end gap-3 border-t border-line bg-bg/95 px-6 py-4 backdrop-blur-sm sm:-mx-10 sm:px-10">
        <Submit pending={pending}>{submitLabel}</Submit>
      </div>
    </form>
  );
}
