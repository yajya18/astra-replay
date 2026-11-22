"use client";

import { Alert, Button } from "@/components/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <Alert title="Something went wrong" action={<Button onClick={reset}>Try again</Button>}>
        {error.message || "An unexpected error occurred while showing this page."}
      </Alert>
    </div>
  );
}
