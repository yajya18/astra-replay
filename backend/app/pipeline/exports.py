"""Stage: assemble the versioned result and write every export format.

result.json (full schema), report.md, report.pdf (with keyframes and the alignment
table), chapters.srt / chapters.vtt (also used by the player), captions.vtt.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import col, delete

from app.db import session_scope
from app.embeddings import embedding_status
from app.models import Export as ExportRow
from app.models import ReferenceStep as ReferenceRow
from app.models import Step as StepRow
from app.models import Video as VideoRow
from app.pipeline.context import JobContext
from app.pipeline.types import (
    AlignmentData,
    HighlightInfo,
    KeyframeInfo,
    MotionData,
    ProviderUsed,
    Result,
    ResultAlignment,
    ResultExport,
    ResultHighlight,
    ResultMedia,
    ResultPhase,
    ResultReference,
    ResultStats,
    ResultStep,
    ResultVideo,
    ResultWindow,
    StepData,
    SummaryData,
    TranscriptSegment,
    UnderTheHood,
    WindowResult,
    WorkVideo,
)

EXPORT_FILES: dict[str, tuple[str, str]] = {
    "json": ("result.json", "JSON (full result)"),
    "md": ("report.md", "Markdown report"),
    "pdf": ("report.pdf", "PDF report"),
    "srt": ("chapters.srt", "SRT chapters"),
    "vtt": ("chapters.vtt", "WebVTT chapters"),
    "mp4": ("highlights.mp4", "Highlight reel (MP4)"),
}


def clock(seconds: float) -> str:
    s = max(0, round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _ts(seconds: float, sep: str) -> str:
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt(entries: list[tuple[float, float, str]]) -> str:
    blocks = [
        f"{i}\n{_ts(a, ',')} --> {_ts(b, ',')}\n{text}\n"
        for i, (a, b, text) in enumerate(entries, 1)
    ]
    return "\n".join(blocks)


def vtt(entries: list[tuple[float, float, str]], ids: bool = True) -> str:
    out = ["WEBVTT", ""]
    for i, (a, b, text) in enumerate(entries, 1):
        if ids:
            out.append(f"step-{i}")
        out.append(f"{_ts(a, '.')} --> {_ts(b, '.')}")
        out.append(text.replace("-->", "->"))
        out.append("")
    return "\n".join(out)


def _downsample(times: list[float], values: list[float], points: int = 400) -> list[list[float]]:
    if not times:
        return []
    step = max(1, len(times) // points)
    return [[round(times[i], 2), round(values[i], 3)] for i in range(0, len(times), step)]


def build_result(
    ctx: JobContext,
    work: WorkVideo,
    motion: MotionData,
    actions: list[WindowResult],
    steps: list[StepData],
    summary: SummaryData,
    alignment: AlignmentData | None,
    keyframes: list[KeyframeInfo],
    highlight: HighlightInfo | None,
    transcript: list[TranscriptSegment],
) -> Result:
    s = ctx.settings
    kf = {k.order: k for k in keyframes}
    phase_of: dict[int, tuple[str, int]] = {}
    phases: list[ResultPhase] = []
    for idx, p in enumerate(summary.phases):
        phases.append(
            ResultPhase(
                name=p.name, start_step=p.start_order, end_step=p.end_order, color_index=idx % 6
            )
        )
        for order in range(p.start_order, p.end_order + 1):
            phase_of[order] = (p.name, idx)
    ref_of: dict[int, int] = {}
    if alignment:
        for r in alignment.reference:
            for order in r.matched_steps:
                ref_of[order] = r.index
    result_steps: list[ResultStep] = []
    for st, title in zip(steps, summary.titles, strict=False):
        k = kf.get(st.order)
        name, pidx = phase_of.get(st.order, ("", 0))
        result_steps.append(
            ResultStep(
                id=st.id,
                order=st.order,
                start=st.start,
                end=st.end,
                duration=round(st.duration, 3),
                title=title,
                verb=st.verb,
                object=st.object,
                tool=st.tool,
                hands=st.hands,
                description=st.description,
                confidence=st.confidence,
                phase=name,
                phase_index=pidx,
                transcript=st.transcript,
                window_ids=st.window_ids,
                keyframe_url=ctx.media_url(k.webp) if k else None,
                keyframe_jpg_url=ctx.media_url(k.jpg) if k else None,
                clip_url=ctx.media_url(f"clips/step_{st.order:02d}.mp4")
                if ctx.path(f"clips/step_{st.order:02d}.mp4").exists()
                else None,
                alignment=alignment.step_status.get(st.order) if alignment else None,
                reference_index=ref_of.get(st.order),
            )
        )
    hl_duration = highlight.duration if highlight else 0.0
    stats = ResultStats(
        original_duration=round(work.duration, 2),
        highlight_duration=round(hl_duration, 2),
        compression_ratio=round(work.duration / hl_duration, 2) if hl_duration > 0 else 0.0,
        step_count=len(steps),
        idle_removed_s=round(motion.idle_seconds, 2),
        processing_s=round(sum(ctx.stage_timings.values()), 2),
        windows_analyzed=len(actions),
    )
    probe = ctx.read_json("probe.json") if ctx.exists("probe.json") else {}
    return Result(
        job_id=ctx.job_id,
        title=ctx.title or summary.task_name,
        task_name=summary.task_name,
        summary=summary.summary,
        mock_mode=s.vlm_provider == "mock" or s.llm_provider == "mock",
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        video=ResultVideo(
            url=ctx.media_url(work.filename),
            duration=work.duration,
            width=work.width,
            height=work.height,
            fps=work.fps,
            has_audio=work.has_audio,
            source_codec=str(probe.get("codec", "")),
            rotation=int(probe.get("rotation", 0) or 0),
            variable_frame_rate=bool(probe.get("variable_frame_rate", False)),
        ),
        stats=stats,
        phases=phases,
        steps=result_steps,
        alignment=(
            ResultAlignment(
                verdict=alignment.verdict,
                completed=alignment.completed,
                total=alignment.total,
                reference=[ResultReference(**r.model_dump()) for r in alignment.reference],
                extra_steps=alignment.extra_steps,
            )
            if alignment
            else None
        ),
        highlight=(
            ResultHighlight(
                url=ctx.media_url(highlight.filename),
                thumbnail_url=ctx.media_url(highlight.thumbnail),
                duration=highlight.duration,
                target=highlight.target,
            )
            if highlight
            else None
        ),
        media=ResultMedia(
            video_url=ctx.media_url(work.filename),
            chapters_vtt_url=ctx.media_url("chapters.vtt"),
            captions_vtt_url=ctx.media_url("captions.vtt"),
            poster_url=ctx.media_url(keyframes[0].jpg) if keyframes else None,
        ),
        exports=[],
        transcript=transcript,
        under_the_hood=UnderTheHood(
            vlm=ProviderUsed(name=s.vlm_provider, model=s.model_for("vlm")),
            llm=ProviderUsed(name=s.llm_provider, model=s.model_for("llm")),
            embedding=embedding_status(),
            prompt_version=s.prompt_version,
            stage_timings=dict(ctx.stage_timings),
            windows=[
                ResultWindow(
                    id=w.window.id,
                    start=w.window.start,
                    end=w.window.end,
                    frames=len(w.window.frame_files),
                    motion=w.window.motion,
                    is_idle=w.action.is_idle,
                    verb=w.action.verb,
                    object=w.action.object,
                    tool=w.action.tool,
                    description=w.action.description,
                    confidence=w.action.confidence,
                    cached=w.cached,
                )
                for w in actions
            ],
            idle_spans=motion.idle_spans,
            scene_cuts=motion.scene_cuts,
            motion_curve=_downsample(motion.times, motion.smooth),
            motion_threshold=motion.threshold,
            summary_source=summary.source,
            transcript_available=bool(transcript),
        ),
    )


# ------------------------------------------------------------------ text exports


def markdown_report(r: Result) -> str:
    vlm, llm = r.under_the_hood.vlm, r.under_the_hood.llm
    lines = [f"# {r.task_name}", "", r.summary, ""]
    if r.mock_mode:
        lines += ["> Generated in **mock mode** (offline demo provider).", ""]
    st = r.stats
    lines += [
        "## Stats",
        "",
        "| Original | Highlight reel | Compression | Steps | Idle removed | Processing |",
        "|---|---|---|---|---|---|",
        f"| {clock(st.original_duration)} | {clock(st.highlight_duration)} | "
        f"{st.compression_ratio:g}x | {st.step_count} | {clock(st.idle_removed_s)} | "
        f"{st.processing_s:.0f}s |",
        "",
    ]
    for phase in r.phases:
        lines += [f"## {phase.name}", ""]
        for s in r.steps:
            if phase.start_step <= s.order <= phase.end_step:
                badge = f" — *{s.alignment.replace('_', ' ')}*" if s.alignment else ""
                tool = f" · tool: {s.tool}" if s.tool else ""
                lines.append(
                    f"{s.order}. **{s.title}** ({clock(s.start)}–{clock(s.end)}, "
                    f"{s.duration:.0f}s){badge}  \n   `{s.verb}` · {s.object or '—'}{tool}. "
                    f"{s.description}"
                )
        lines.append("")
    if r.alignment:
        lines += [
            "## Procedure check",
            "",
            r.alignment.verdict,
            "",
            "| # | Reference step | Status | Matched steps |",
            "|---|---|---|---|",
        ]
        for ref in r.alignment.reference:
            matched = ", ".join(str(m) for m in ref.matched_steps) or "—"
            lines.append(
                f"| {ref.index} | {ref.text} | {ref.status.replace('_', ' ')} | {matched} |"
            )
        lines.append("")
    lines += [
        "---",
        f"Generated by Replay · providers: {vlm.name}/{vlm.model} (vision), "
        f"{llm.name}/{llm.model} (text)",
        "",
    ]
    return "\n".join(lines)


def pdf_report(r: Result, job_dir: Path, out: Path) -> None:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    vlm, llm = r.under_the_hood.vlm, r.under_the_hood.llm
    fonts = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("VeraBd", str(fonts / "VeraBd.ttf")))
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Vera", fontSize=9.5, leading=13
    )
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#555b70"))
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontName="VeraBd", fontSize=20, leading=24)
    h2 = ParagraphStyle(
        "h2",
        parent=base["Heading2"],
        fontName="VeraBd",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#4338ca"),
    )
    strong = ParagraphStyle("strong", parent=body, fontName="VeraBd")

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(escape(text), style)

    story: list[object] = [p(r.task_name, h1), p(r.summary)]
    if r.mock_mode:
        story.append(p("Generated in mock mode (offline demo provider).", small))
    story.append(Spacer(1, 4 * mm))
    st = r.stats
    stats = Table(
        [
            ["Original", "Highlight", "Compression", "Steps", "Idle removed", "Processing"],
            [
                clock(st.original_duration),
                clock(st.highlight_duration),
                f"{st.compression_ratio:g}x",
                str(st.step_count),
                clock(st.idle_removed_s),
                f"{st.processing_s:.0f}s",
            ],
        ],
        hAlign="LEFT",
    )
    stats.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "VeraBd"),
                ("FONTNAME", (0, 1), (-1, 1), "Vera"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e7fd")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe1ec")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [stats, Spacer(1, 5 * mm)]
    for phase in r.phases:
        story.append(p(phase.name, h2))
        for s in r.steps:
            if not phase.start_step <= s.order <= phase.end_step:
                continue
            img_cell: object = ""
            if s.keyframe_jpg_url:
                rel = s.keyframe_jpg_url.split(f"/media/jobs/{r.job_id}/", 1)[-1]
                path = job_dir / rel
                if path.exists():
                    ratio = r.video.height / max(1, r.video.width)
                    img_cell = Image(str(path), width=42 * mm, height=42 * mm * ratio)
            badge = f"  [{s.alignment.replace('_', ' ')}]" if s.alignment else ""
            text = [
                p(f"{s.order}. {s.title}{badge}", strong),
                p(
                    f"{clock(s.start)}–{clock(s.end)} ({s.duration:.0f}s) · {s.verb} · "
                    f"{s.object or '—'}{' · ' + s.tool if s.tool else ''} · "
                    f"confidence {s.confidence:.0%}",
                    small,
                ),
                p(s.description),
            ]
            row = Table([[img_cell, text]], colWidths=[46 * mm, None], hAlign="LEFT")
            row.setStyle(
                TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 3)])
            )
            story.append(KeepTogether([row, Spacer(1, 2 * mm)]))
    if r.alignment:
        story += [p("Procedure check", h2), p(r.alignment.verdict), Spacer(1, 2 * mm)]
        rows = [["#", "Reference step", "Status", "Matched"]]
        for ref in r.alignment.reference:
            rows.append(
                [
                    str(ref.index),
                    Paragraph(escape(ref.text), body),
                    ref.status.replace("_", " "),
                    ", ".join(str(m) for m in ref.matched_steps) or "—",
                ]
            )
        table = Table(rows, colWidths=[10 * mm, 100 * mm, 30 * mm, 25 * mm], hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, 0), "VeraBd"),
            ("FONTNAME", (0, 1), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe1ec")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e7fd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        for i, ref in enumerate(r.alignment.reference, start=1):
            color = {"done": "#dcf5f1", "missed": "#fde4e4", "out_of_order": "#fdeedd"}[ref.status]
            style.append(("BACKGROUND", (2, i), (2, i), colors.HexColor(color)))
        table.setStyle(TableStyle(style))
        story.append(table)
    story += [
        Spacer(1, 6 * mm),
        p(
            f"Generated by Replay · vision: {vlm.name}/{vlm.model} · text: {llm.name}/{llm.model}",
            small,
        ),
    ]
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        title=r.task_name,
        author="Replay",
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    doc.build(story)


def persist_rows(ctx: JobContext, result: Result) -> None:
    with session_scope() as session:
        session.exec(delete(StepRow).where(col(StepRow.job_id) == ctx.job_id))
        session.exec(delete(ReferenceRow).where(col(ReferenceRow.job_id) == ctx.job_id))
        session.exec(delete(ExportRow).where(col(ExportRow.job_id) == ctx.job_id))
        for s in result.steps:
            session.add(
                StepRow(
                    job_id=ctx.job_id,
                    order=s.order,
                    start=s.start,
                    end=s.end,
                    title=s.title,
                    verb=s.verb,
                    object=s.object,
                    tool=s.tool,
                    description=s.description,
                    phase=s.phase,
                    confidence=s.confidence,
                    alignment=s.alignment,
                )
            )
        if result.alignment:
            for ref in result.alignment.reference:
                session.add(
                    ReferenceRow(
                        job_id=ctx.job_id,
                        order=ref.index,
                        text=ref.text,
                        status=ref.status,
                        matched_steps_json=json.dumps(ref.matched_steps),
                    )
                )
        for e in result.exports:
            session.add(
                ExportRow(
                    job_id=ctx.job_id, kind=e.kind, filename=e.filename, size_bytes=e.size_bytes
                )
            )
        video = session.get(VideoRow, ctx.job_id)
        if video is not None:
            video.duration = result.video.duration
            video.width = result.video.width
            video.height = result.video.height
            video.fps = result.video.fps
            session.add(video)
        session.commit()


def run(
    ctx: JobContext,
    work: WorkVideo,
    motion: MotionData,
    actions: list[WindowResult],
    steps: list[StepData],
    summary: SummaryData,
    alignment: AlignmentData | None,
    keyframes: list[KeyframeInfo],
    highlight: HighlightInfo | None,
    transcript: list[TranscriptSegment],
) -> Result:
    result = build_result(
        ctx, work, motion, actions, steps, summary, alignment, keyframes, highlight, transcript
    )
    chapters = [(s.start, s.end, f"{s.order}. {s.title}") for s in result.steps]
    ctx.path("chapters.srt").write_text(srt(chapters), encoding="utf-8", newline="\n")
    ctx.path("chapters.vtt").write_text(vtt(chapters), encoding="utf-8", newline="\n")
    captions = (
        [(t.start, t.end, t.text) for t in transcript]
        if transcript
        else [(s.start, s.end, f"Step {s.order}: {s.title}") for s in result.steps]
    )
    ctx.path("captions.vtt").write_text(vtt(captions, ids=False), encoding="utf-8", newline="\n")
    ctx.progress(0.3, "Writing reports")
    ctx.path("report.md").write_text(markdown_report(result), encoding="utf-8", newline="\n")
    pdf_report(result, ctx.job_dir, ctx.path("report.pdf"))
    ctx.progress(0.8, "Writing result")

    def exports_list(json_size: int) -> list[ResultExport]:
        out = []
        for kind, (filename, label) in EXPORT_FILES.items():
            path = ctx.path(filename)
            if kind != "json" and not path.exists():
                continue
            out.append(
                ResultExport(
                    kind=kind,
                    label=label,
                    url=f"/api/jobs/{ctx.job_id}/exports/{kind}",
                    filename=filename,
                    size_bytes=json_size if kind == "json" else path.stat().st_size,
                )
            )
        return out

    size = 0
    for _ in range(3):  # the JSON lists its own size; converge in a couple of passes
        result = result.model_copy(update={"exports": exports_list(size)})
        text = result.model_dump_json(indent=2)
        if len(text.encode()) == size:
            break
        size = len(text.encode())
    ctx.write_json("result.json", result)
    persist_rows(ctx, result)
    ctx.progress(1.0, "Done")
    return result
