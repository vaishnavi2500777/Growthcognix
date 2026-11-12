/* eslint-disable @next/next/no-img-element */
export function Logo({ className = "h-8" }: { className?: string }) {
  return (
    <span className="inline-flex">
      <img src="/logo-light.svg" alt="GrowthCognix" className={`logo-light w-auto ${className}`} />
      <img src="/logo-dark.svg" alt="GrowthCognix" className={`logo-dark w-auto ${className}`} />
    </span>
  );
}
