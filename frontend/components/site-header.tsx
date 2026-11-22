import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Logo } from "@/components/logo";

const NAV = [
  { href: "/demo", label: "Demos", short: "Demos" },
  { href: "/about", label: "How it works", short: "About" },
  { href: "/xr", label: "XR preview", short: "XR" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold" aria-label="Replay home">
          <Logo className="h-7 w-7" />
          <span className="text-lg tracking-tight">Replay</span>
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 sm:gap-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-2 py-1.5 text-sm text-muted transition hover:bg-surface-2 hover:text-foreground sm:px-3"
            >
              <span className="hidden sm:inline">{item.label}</span>
              <span className="sm:hidden">{item.short}</span>
            </Link>
          ))}
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
