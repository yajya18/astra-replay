import Link from "next/link";
import { ArrowRight, Hand, ShieldCheck, Smartphone, Sparkles, Upload } from "lucide-react";
import { UploadCard } from "@/components/upload/upload-card";
import { DemoGallery } from "@/components/demo-gallery";

const FLOW = [
  {
    icon: Smartphone,
    title: "Record",
    text: "Film the task first-person: phone on your chest, head, or at eye level.",
  },
  {
    icon: Upload,
    title: "Upload",
    text: "Add the video, plus the recipe or procedure you meant to follow if you have one.",
  },
  {
    icon: Sparkles,
    title: "Replay",
    text: "Get a searchable, action-by-action recap with a highlight reel and a procedure check.",
  },
];

export default function Home() {
  return (
    <>
      <section className="hero-glow border-b border-border">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:py-16 lg:grid-cols-[1.05fr_1fr] lg:items-start">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted">
              <Hand className="h-3.5 w-3.5 text-accent" aria-hidden /> Summaries built from actions
            </p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
              Your long how-to video, replayed as{" "}
              <span className="text-accent">the actions you did</span>.
            </h1>
            <p className="mt-4 max-w-xl text-lg text-muted">
              Replay turns a first-person recording of cooking, assembly, repair or a lab procedure
              into short steps, each one a{" "}
              <strong className="text-foreground">verb + object + tool</strong>, so you can search
              it, check it against the recipe and share a one-minute recap.
            </p>
            <ol className="mt-8 grid gap-3 sm:grid-cols-3" aria-label="How Replay works">
              {FLOW.map((step, i) => (
                <li
                  key={step.title}
                  className="relative rounded-xl border border-border bg-surface p-4"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-soft text-accent">
                      <step.icon className="h-4 w-4" aria-hidden />
                    </span>
                    <span className="font-semibold">
                      {i + 1}. {step.title}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted">{step.text}</p>
                </li>
              ))}
            </ol>
            <div className="mt-6 flex flex-wrap gap-3 text-sm">
              <Link
                href="/demo"
                className="inline-flex items-center gap-1 font-medium text-accent hover:underline"
              >
                Browse demo results <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
              <Link
                href="/about"
                className="inline-flex items-center gap-1 font-medium text-muted hover:text-foreground"
              >
                How the pipeline works
              </Link>
            </div>
          </div>
          <div id="upload">
            <UploadCard />
            <p className="mt-3 flex items-start gap-2 text-xs text-muted">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
              Privacy: your video is processed only for this session and is deleted automatically
              after 24 hours. Nothing is used for training.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12" aria-labelledby="demos-heading">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="demos-heading" className="text-2xl font-semibold tracking-tight">
              Try a demo
            </h2>
            <p className="mt-1 text-muted">Precomputed results open instantly, no upload needed.</p>
          </div>
          <Link href="/demo" className="text-sm font-medium text-accent hover:underline">
            All demos
          </Link>
        </div>
        <DemoGallery limit={3} />
      </section>
    </>
  );
}
