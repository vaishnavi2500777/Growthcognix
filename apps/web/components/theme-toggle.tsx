"use client";

export function ThemeToggle() {
  function toggle() {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    document.cookie = `gc-theme=${next}; path=/; max-age=31536000; samesite=lax`;
  }
  return (
    <button type="button" onClick={toggle} aria-label="Switch light or dark theme"
      className="inline-flex h-10 w-10 items-center justify-center rounded-[10px] border border-line text-muted hover:text-ink hover:bg-surface-2">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" />
      </svg>
    </button>
  );
}
