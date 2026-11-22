import type { Metadata } from "next";
import Link from "next/link";
import { Glasses, Hand, Lock, Search, Timer, Wand2 } from "lucide-react";
import { ApiDocsLink } from "@/components/api-docs-link";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { XRPreviewSection } from "@/components/xr/xr-preview-section";
import { Card } from "@/components/ui";

export const metadata: Metadata = { title: "How it works" };

const PROBLEMS = [
  {
    icon: Timer,
    title: "Long, unedited footage",
    text: "A 10-minute first-person recording of a recipe or repair is mostly reaching, waiting and looking around.",
  },
  {
    icon: Search,
    title: "Hard to search",
    text: "Scene-change and transcript-based summaries miss what matters: what your hands actually did.",
  },
  {
    icon: Hand,
    title: "Did I skip a step?",
    text: "Procedures (recipes, assembly, lab protocols) need a check that you did every step, in order.",
  },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-14 px-4 py-10">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">How Replay works</h1>
        <p className="mt-3 max-w-3xl text-lg text-muted">
          Replay summarises a video around <strong className="text-foreground">actions</strong>,
          each described as <strong className="text-foreground">verb + object + tool</strong>{" "}
          (&ldquo;chop · onion · knife&rdquo;), instead of scene changes or transcript text. That
          makes the recap searchable by what you did, and lets it be checked against the procedure
          you meant to follow.
        </p>
      </section>

      <section aria-labelledby="problem">
        <h2 id="problem" className="text-xl font-semibold">
          The problem
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {PROBLEMS.map((p) => (
            <Card key={p.title} className="p-5">
              <p.icon className="h-5 w-5 text-accent" aria-hidden />
              <h3 className="mt-3 font-semibold">{p.title}</h3>
              <p className="mt-1 text-sm text-muted">{p.text}</p>
            </Card>
          ))}
        </div>
      </section>

      <section aria-labelledby="pipeline">
        <h2 id="pipeline" className="text-xl font-semibold">
          The pipeline
        </h2>
        <p className="mt-2 max-w-3xl text-muted">
          Idle time is removed using the video&apos;s own motion curve. The rest is cut into
          overlapping 4-second windows that never cross a hard scene cut. A vision-language model
          labels each window with a strict-JSON action, and windows are merged into steps by
          matching verbs and objects and by embedding similarity. A text model then writes titles
          and phases; its output is validated, and deterministic titles are used if it drops or
          reorders a step. With a reference procedure, steps are aligned using Hungarian matching
          and a longest-increasing-subsequence order check.
        </p>
        <div className="mt-5">
          <PipelineDiagram />
        </div>
      </section>

      <section aria-labelledby="xr" className="space-y-4">
        <h2 id="xr" className="flex items-center gap-2 text-xl font-semibold">
          <Glasses className="h-5 w-5 text-accent" aria-hidden /> The XR vision
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="p-5">
            <h3 className="font-semibold">Egocentric by design</h3>
            <p className="mt-1 text-sm text-muted">
              The pipeline already expects first-person footage, so the same steps work on video
              from Galaxy XR headsets or smart glasses, with no phone needed.
            </p>
          </Card>
          <Card className="p-5">
            <h3 className="flex items-center gap-2 font-semibold">
              <Lock className="h-4 w-4 text-success" aria-hidden /> Private, on-device option
            </h3>
            <p className="mt-1 text-sm text-muted">
              The provider layer is swappable. The Ollama provider runs a local vision model, so
              video never has to leave the device.
            </p>
          </Card>
          <Card className="p-5">
            <h3 className="flex items-center gap-2 font-semibold">
              <Wand2 className="h-4 w-4 text-accent" aria-hidden /> Step cards in space
            </h3>
            <p className="mt-1 text-sm text-muted">
              In a headset, step cards can float beside your workspace and guide you live. Preview
              it below, or{" "}
              <Link href="/xr" className="text-accent hover:underline">
                open the full XR view
              </Link>
              .
            </p>
          </Card>
        </div>
        <XRPreviewSection />
      </section>

      <section aria-labelledby="team">
        <h2 id="team" className="text-xl font-semibold">
          Team and links
        </h2>
        <Card className="mt-4 p-5 text-sm">
          <p>
            Built by Team Astra, Thapar Institute of Engineering and Technology, for the Samsung
            PRISM XR Hackathon, track 4, &ldquo;Action Aware Video Summarization&rdquo;.
          </p>
          <p className="mt-2 text-muted">Yajya Arora, Sandhi Gahlot, Hardik Jain, Durva.</p>
          <ul className="mt-3 flex flex-wrap gap-4">
            <li>
              <Link href="/" className="font-medium text-accent hover:underline">
                Upload a video
              </Link>
            </li>
            <li>
              <Link href="/demo" className="font-medium text-accent hover:underline">
                Demo results
              </Link>
            </li>
            <li>
              <Link href="/xr" className="font-medium text-accent hover:underline">
                XR preview
              </Link>
            </li>
            <li>
              <a
                href="https://github.com/yajya18/astra-replay"
                className="font-medium text-accent hover:underline"
              >
                Source on GitHub
              </a>
            </li>
            <li>
              <ApiDocsLink className="font-medium text-accent hover:underline" />
            </li>
          </ul>
        </Card>
      </section>
    </div>
  );
}
