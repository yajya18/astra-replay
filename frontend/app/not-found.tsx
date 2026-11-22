import Link from "next/link";
import { buttonClass } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-24 text-center">
      <p className="text-sm font-semibold text-accent">404</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-2 text-muted">That page doesn&apos;t exist, or the job was deleted.</p>
      <Link href="/" className={`${buttonClass("primary")} mt-6`}>
        Back to Replay
      </Link>
    </div>
  );
}
