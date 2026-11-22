export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d="M11 9.5v13l10-6.5z" fill="var(--accent-foreground)" />
      <rect
        x="8"
        y="24.5"
        width="4"
        height="2"
        rx="1"
        fill="var(--accent-foreground)"
        opacity=".9"
      />
      <rect
        x="14"
        y="24.5"
        width="6"
        height="2"
        rx="1"
        fill="var(--accent-foreground)"
        opacity=".7"
      />
      <rect
        x="22"
        y="24.5"
        width="2.5"
        height="2"
        rx="1"
        fill="var(--accent-foreground)"
        opacity=".5"
      />
    </svg>
  );
}
