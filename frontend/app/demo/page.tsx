import type { Metadata } from "next";
import { DemoGallery } from "@/components/demo-gallery";

export const metadata: Metadata = { title: "Demos" };

export default function DemoPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Demo results</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Precomputed recaps of first-person task videos. Open one to explore the chapters, search,
        the procedure check and the highlight reel. Demos with a reference procedure show how Replay
        flags missed and out-of-order steps.
      </p>
      <div className="mt-8">
        <DemoGallery />
      </div>
    </div>
  );
}
