"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/dashboard", label: "Overview", d: "M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z" },
  { href: "/agents", label: "Agents", d: "M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm-7 16c.6-3.4 3.5-5.5 7-5.5s6.4 2.1 7 5.5" },
  { href: "/business", label: "Business profile", d: "M4 20V8l8-4 8 4v12M9 20v-6h6v6M4 20h16" },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="flex gap-1 md:flex-col">
      {ITEMS.map((i) => {
        const active = path.startsWith(i.href);
        return (
          <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
            className={`flex h-10 items-center gap-3 rounded-[10px] px-3 text-[14px] transition ${active
              ? "bg-surface text-ink border border-line font-medium" : "text-muted hover:text-ink hover:bg-surface-2 border border-transparent"}`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={i.d} /></svg>
            <span className="whitespace-nowrap">{i.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
