"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { createXRStore } from "@react-three/xr";
import { Glasses, Loader2, ScanEye } from "lucide-react";
import { api } from "@/lib/api";
import { SAMPLE_STEPS, stepsFromResult } from "@/components/xr/xr-data";
import { Badge, Button, Card } from "@/components/ui";

const XRScene = dynamic(() => import("@/components/xr/xr-scene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-muted">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> Loading 3D scene…
    </div>
  ),
});

type Support = { vr: boolean; ar: boolean; checked: boolean };

function useXRSupport(): Support {
  const [support, setSupport] = useState<Support>({ vr: false, ar: false, checked: false });
  useEffect(() => {
    const xr = (
      navigator as Navigator & { xr?: { isSessionSupported(mode: string): Promise<boolean> } }
    ).xr;
    let alive = true;
    const check = (mode: string) =>
      xr ? xr.isSessionSupported(mode).catch(() => false) : Promise.resolve(false);
    Promise.all([check("immersive-vr"), check("immersive-ar")]).then(([vr, ar]) => {
      if (alive) setSupport({ vr, ar, checked: true });
    });
    return () => {
      alive = false;
    };
  }, []);
  return support;
}

/** Loads a result (the given job, else the first demo) and shows its steps as 3D cards. */
export function XRViewer({ jobId, height = "70vh" }: { jobId?: string; height?: string }) {
  const store = useMemo(() => createXRStore({ emulate: false }), []);
  const support = useXRSupport();
  const [selected, setSelected] = useState<number | null>(null);

  const { data: demos } = useQuery({ queryKey: ["demos"], queryFn: api.demos, enabled: !jobId });
  const targetId = jobId ?? demos?.find((d) => d.status === "completed")?.job_id;
  const { data: result, isFetching } = useQuery({
    queryKey: ["result", targetId],
    queryFn: () => api.result(targetId!),
    enabled: !!targetId,
  });

  const steps = result ? stepsFromResult(result) : SAMPLE_STEPS;
  const title = result?.task_name ?? "Sample timeline";
  const chosen = steps.find((s) => s.order === selected);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {result ? (
            <>
              <Badge tone="accent">{result.steps.length} steps</Badge>
              <Link
                href={`/results/${result.job_id}`}
                className="font-medium text-accent hover:underline"
              >
                {result.task_name}
              </Link>
            </>
          ) : (
            <Badge tone="warning">{isFetching ? "Loading result…" : "Sample timeline"}</Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => store.enterVR()} disabled={!support.vr}>
            <Glasses className="h-4 w-4" aria-hidden /> Enter VR
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => store.enterAR()}
            disabled={!support.ar}
          >
            <ScanEye className="h-4 w-4" aria-hidden /> Enter AR
          </Button>
        </div>
      </div>
      <div
        className="overflow-hidden rounded-2xl border border-border bg-[#0b0c12]"
        style={{ height }}
        role="img"
        aria-label={`3D view of ${steps.length} step cards for ${title}. Drag to look around; click a card for details.`}
      >
        <XRScene
          steps={steps}
          title={title}
          store={store}
          selected={selected}
          onSelect={setSelected}
        />
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3 text-xs text-muted">
        <p>
          Drag to orbit, scroll to zoom.{" "}
          {support.checked && !support.vr && !support.ar
            ? "WebXR isn't available in this browser; open this page on a headset (e.g. Galaxy XR) to step inside."
            : "On a WebXR device, Enter VR/AR places the cards around you."}
        </p>
      </div>
      {chosen ? (
        <Card className="p-3 text-sm" aria-live="polite">
          <p className="font-semibold">
            Step {chosen.order}: {chosen.title}
          </p>
          <p className="text-muted">
            {chosen.time} · {chosen.phase}
            {chosen.description ? ` · ${chosen.description}` : ""}
          </p>
        </Card>
      ) : null}
    </div>
  );
}
