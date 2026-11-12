import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_480px]">
      <main className="flex flex-col px-6 py-6 sm:px-10">
        <header className="flex items-center justify-between">
          <Logo />
          <ThemeToggle />
        </header>
        <div className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-[400px]">{children}</div>
        </div>
        <footer className="text-xs text-muted">© 2026 GrowthCognix · Bengaluru</footer>
      </main>
      <aside className="hidden border-l border-line bg-surface-2 p-12 lg:flex lg:flex-col lg:justify-end">
        <p className="eyebrow">Supervised AI</p>
        <h2 className="mt-4 text-[34px] leading-[1.1] tracking-[-0.02em] font-medium">
          Marketing that thinks.<br />
          <span className="font-serif italic text-primary">Growth you approve.</span>
        </h2>
        <ol className="mt-10 space-y-5 text-[15px]">
          {[
            ["01", "Tell us about your business", "Industry, products, services and customers."],
            ["02", "Agents get to work", "Research, plans and content, prepared for you."],
            ["03", "Nothing goes out without you", "Publishing, sending and spending wait for approval."],
          ].map(([n, t, d]) => (
            <li key={n} className="grid grid-cols-[32px_1fr] gap-x-2">
              <span className="font-mono text-xs text-muted pt-1">{n}</span>
              <div>
                <p className="font-medium">{t}</p>
                <p className="text-muted">{d}</p>
              </div>
            </li>
          ))}
        </ol>
      </aside>
    </div>
  );
}
