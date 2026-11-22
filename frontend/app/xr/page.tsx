import type { Metadata } from "next";
import { Suspense } from "react";
import { XRViewer } from "@/components/xr/xr-viewer";
import { Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "XR preview" };

export default function XRPage({ searchParams }: PageProps<"/xr">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">XR preview</h1>
      <p className="mt-1 max-w-3xl text-muted">
        Your step timeline as cards floating in 3D space. It works in a normal browser, and on WebXR
        headsets you can step inside it. The same pipeline can take egocentric video from Galaxy XR
        headsets or smart glasses.
      </p>
      <div className="mt-6">
        <Suspense fallback={<Skeleton className="h-[70vh] w-full" />}>
          {searchParams.then((sp) => {
            const job =
              typeof sp.job === "string" && /^[a-f0-9]{32}$/.test(sp.job) ? sp.job : undefined;
            return <XRViewer jobId={job} />;
          })}
        </Suspense>
      </div>
    </div>
  );
}
