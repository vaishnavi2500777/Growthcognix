import type { Metadata } from "next";
import { BusinessForm } from "@/components/business-form";
import { PageHead } from "@/components/page-head";
import { api, apiOrLogin } from "@/lib/api";
import type { BusinessProfile, Industry } from "@/lib/types";

export const metadata: Metadata = { title: "Business profile" };

export default async function Business() {
  const [profile, industries] = await Promise.all([
    apiOrLogin<BusinessProfile>("/business-profile"),
    api<Industry[]>("/industries", { auth: false }),
  ]);
  return (
    <>
      <PageHead eyebrow="Settings" title="Business profile">
        Every agent starts from this. Keep it current and specific.
      </PageHead>
      <BusinessForm industries={industries} initial={profile} next="/dashboard" submitLabel="Save changes" />
    </>
  );
}
