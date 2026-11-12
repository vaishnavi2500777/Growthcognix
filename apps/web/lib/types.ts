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
