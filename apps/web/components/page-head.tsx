export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className="mb-10">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="mt-3 text-[30px] leading-tight tracking-[-0.02em] font-medium">{title}</h1>
      {children && <div className="mt-2 max-w-[620px] text-muted">{children}</div>}
    </header>
  );
}

export function Status({ tone, children }: { tone: "done" | "todo" | "wait"; children: React.ReactNode }) {
  const dot = { done: "bg-success", todo: "bg-line", wait: "bg-warning" }[tone];
  return (
    <span className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border border-line px-2.5 py-1 text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />{children}
    </span>
  );
}
