import type { Metadata } from "next";
import { Suspense } from "react";
import { ResultsSkeleton, ResultsView } from "@/components/results/results-view";

export const metadata: Metadata = { title: "Results" };

export default function ResultsPage({ params }: PageProps<"/results/[id]">) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <Suspense fallback={<ResultsSkeleton />}>
        {params.then(({ id }) => (
          <ResultsView jobId={id} />
        ))}
      </Suspense>
    </div>
  );
}
