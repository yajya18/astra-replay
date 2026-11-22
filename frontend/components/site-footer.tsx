import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
        <p>Replay · action-aware video summarization · Samsung PRISM XR Hackathon</p>
        <nav aria-label="Footer" className="flex gap-4">
          <Link href="/about" className="hover:text-foreground">
            About
          </Link>
          <Link href="/demo" className="hover:text-foreground">
            Demos
          </Link>
          <Link href="/xr" className="hover:text-foreground">
            XR
          </Link>
        </nav>
      </div>
    </footer>
  );
}
