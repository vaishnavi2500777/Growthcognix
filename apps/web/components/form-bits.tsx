"use client";

import { startTransition } from "react";

/** Submit without React's automatic form reset, so typed values survive a validation error. */
export function keepValues(action: (fd: FormData) => void) {
  return (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    startTransition(() => action(fd));
  };
}

export function Submit({ children, className = "", pending = false }: {
  children: React.ReactNode; className?: string; pending?: boolean;
}) {
  return (
    <button type="submit" disabled={pending} className={`btn btn-primary ${className}`}>
      {pending ? "Please wait…" : children}
    </button>
  );
}

export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-[10px] border border-danger/30 bg-danger/10 px-3 py-2.5 text-sm text-danger">
      {message}
    </p>
  );
}

export function FieldError({ message }: { message?: string }) {
  return message ? <small className="!text-danger">{message}</small> : null;
}
