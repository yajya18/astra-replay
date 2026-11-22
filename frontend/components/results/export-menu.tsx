"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, FileJson, FileText, FileType, Film, Subtitles } from "lucide-react";
import { apiUrl } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { ResultExport } from "@/lib/types";
import { Button } from "@/components/ui";

const ICONS: Record<string, typeof FileText> = {
  json: FileJson,
  md: FileText,
  pdf: FileType,
  srt: Subtitles,
  vtt: Subtitles,
  mp4: Film,
};

export function ExportMenu({ exports }: { exports: ResultExport[] }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <Button
        variant="secondary"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-controls="export-menu"
      >
        <Download className="h-4 w-4" aria-hidden /> Export
        <ChevronDown className="h-4 w-4" aria-hidden />
      </Button>
      {open ? (
        <ul
          id="export-menu"
          className="absolute right-0 z-30 mt-2 w-64 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-xl"
        >
          {exports.map((e) => {
            const Icon = ICONS[e.kind] ?? FileText;
            return (
              <li key={e.kind}>
                <a
                  href={apiUrl(e.url)}
                  download
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-surface-2"
                >
                  <Icon className="h-4 w-4 text-accent" aria-hidden />
                  <span className="flex-1">{e.label}</span>
                  <span className="text-xs text-muted">{formatBytes(e.size_bytes)}</span>
                </a>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
