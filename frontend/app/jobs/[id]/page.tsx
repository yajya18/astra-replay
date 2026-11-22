import type { Metadata } from "next";
import { Suspense } from "react";
import { JobProgress } from "@/components/job/job-progress";
import { Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Processing" };

function Fallback() {
  return (
    <div className="space-y-3" aria-busy="true">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

export default function JobPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <Suspense fallback={<Fallback />}>
        {params.then(({ id }) => (
          <JobProgress jobId={id} />
        ))}
      </Suspense>
    </div>
  );
}
