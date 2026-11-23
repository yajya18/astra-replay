"""Build Astra_Replay_Submission.pptx from template.pptx and team.json.

    uv run --with python-pptx python docs/presentation/build_deck.py

Edit team.json (team, college, members, links) and re-run. template.pptx is the original
hackathon template; it is never modified. Slide order and titles are fixed by the template.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
TEAM = json.loads((HERE / "team.json").read_text(encoding="utf-8"))

BG = RGBColor(0x0A, 0x0E, 0x1A)
PANEL = RGBColor(0x0D, 0x1B, 0x3E)
PANEL_2 = RGBColor(0x13, 0x24, 0x4F)
CYAN = RGBColor(0x00, 0xB4, 0xD8)
BLUE = RGBColor(0x15, 0x65, 0xC0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0xA9, 0xB4, 0xCC)
AMBER = RGBColor(0xFF, 0xB7, 0x4D)
BODY_FONT = "Calibri"
MONO_FONT = "Consolas"


def add_text(slide, x, y, w, h, paras, size=18, color=WHITE, bold=False, font=BODY_FONT,
             anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT, space_after=6):
    """paras: list of str or list of (text, {opts}) or list of runs lists."""
    box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            text, opts = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = opts.get("font", font)
            f.size = Pt(opts.get("size", size))
            f.bold = opts.get("bold", bold)
            f.color.rgb = opts.get("color", color)
    return box


def add_rect(slide, x, y, w, h, fill=PANEL, line=None, shape=MSO_SHAPE.RECTANGLE, radius=None):
    s = slide.shapes.add_shape(shape, Emu(x), Emu(y), Emu(w), Emu(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def bullets(slide, x, y, w, h, items, size=18, gap=9):
    """Cyan square marker + text, one paragraph per item."""
    paras = [[("▪  ", {"color": CYAN, "bold": True}), (t, {})] for t in items]
    return add_text(slide, x, y, w, h, paras, size=size, space_after=gap)


def picture(slide, path, x, y, w=None, h=None, border=True):
    pic = slide.shapes.add_picture(str(path), Emu(x), Emu(y), Emu(w) if w else None,
                                   Emu(h) if h else None)
    if border:
        pic.line.color.rgb = PANEL_2
        pic.line.width = Pt(1)
    return pic


def clear_empty_boxes(slide):
    for sh in list(slide.shapes):
        if sh.has_text_frame and sh.shape_type == 17 and not sh.text_frame.text.strip():
            sh._element.getparent().remove(sh._element)


def set_text(shape, lines, size=None):
    """Replace shape text keeping the first run's formatting."""
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    r0 = p0.runs[0]
    rpr = copy.deepcopy(r0._r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr"))
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    for r in list(p0.runs)[1:]:
        r._r.getparent().remove(r._r)
    r0.text = lines[0]
    for line in lines[1:]:
        p = tf.add_paragraph()
        p._p.insert(0, copy.deepcopy(p0._p.find("{http://schemas.openxmlformats.org/drawingml/2006/main}pPr")))
        r = p.add_run()
        r.text = line
        r._r.insert(0, copy.deepcopy(rpr))
    if size:
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(size)


def find(slide, name):
    return next(s for s in slide.shapes if s.name == name)


W, H = 9144000, 5143500
LM = 365760  # template left margin
TOP = 960000  # first content line under the header rule
BOTTOM = H - 300000


def slide1(s):
    set_text(find(s, "Text 7"), [f"Track {TEAM['track_no']}"], size=12)
    # Arial Black at the template's 72 pt runs into the decorative bars in PowerPoint.
    for run in find(s, "Text 8").text_frame.paragraphs[0].runs:
        run.font.size = Pt(62)
    t10 = find(s, "Text 10")
    t10.width = Emu(4300000)
    t10.height = Emu(1500000)
    set_text(t10, [f"Team {TEAM['team_name']}", TEAM["college"]], size=18)
    t10.top = Emu(2377440)
    members = find(s, "Text Box 22")
    members.left, members.top, members.width = Emu(5122545), Emu(2377440), Emu(3300000)
    members.height = Emu(1600000)
    tf = members.text_frame
    tf.word_wrap = True
    ref_p = tf.paragraphs[0]
    ref_r = ref_p.runs[0]
    ref_r.text = "Members"
    ref_r.font.bold = True
    ref_r.font.color.rgb = CYAN
    ref_r.font.size = Pt(14)
    for name in TEAM["members"]:
        p = tf.add_paragraph()
        r = p.add_run()
        r.text = name
        r.font.size = Pt(20)
        r.font.color.rgb = WHITE
        r.font.name = BODY_FONT
    add_text(s, 502920, 4200000, 7500000, 700000,
             [[(f"{TEAM['project']}: ", {"bold": True, "color": CYAN}),
               (TEAM["tagline"] + ". Track " + TEAM["track_no"] + ", " + TEAM["track_name"] + ".", {})]],
             size=16, color=MUTED)


def slide2(s):
    bullets(s, LM, TOP, 4900000, 3600000, [
        "Phones, helmets and glasses now record hours of first-person footage.",
        "Most of it is reaching, waiting and repeating, so nobody watches it again.",
        "Scene-change and transcript summarisers cut at shots and words. A how-to is a sequence of actions.",
        "Nothing tells you which recipe step you skipped or did out of order.",
    ], size=20, gap=12)
    x = 5600000
    w = W - x - LM
    add_rect(s, x, TOP, w, 1500000, PANEL, line=PANEL_2)
    add_text(s, x + 150000, TOP + 110000, w - 300000, 300000, ["A scene-based summary says"], size=13,
             color=MUTED, bold=True)
    add_text(s, x + 150000, TOP + 480000, w - 300000, 900000,
             ['"cut at 0:23, cut at 0:31"'], size=15, color=WHITE, font=MONO_FONT)
    add_rect(s, x, TOP + 1700000, w, 1500000, PANEL, line=CYAN)
    add_text(s, x + 150000, TOP + 1810000, w - 300000, 300000, ["An action summary says"], size=13,
             color=CYAN, bold=True)
    add_text(s, x + 150000, TOP + 2180000, w - 300000, 900000,
             ['"heat · butter · pan"', ('0:23 to 0:31', {'size': 14, 'color': MUTED, 'font': BODY_FONT})],
             size=15, color=WHITE, font=MONO_FONT)


def slide3(s):
    bullets(s, LM, TOP, 4050000, 3700000, [
        "Upload a first-person video and, if you have one, the recipe you meant to follow.",
        "Idle time is dropped using the video's own motion curve.",
        "A vision-language model labels each window: verb, object, tool.",
        "Windows merge into steps with times, keyframes and clips.",
        "You get search with timestamps, a procedure check, a captioned reel and exports.",
    ], size=17, gap=10)
    pw = 4200000
    px = W - LM - pw
    ph = int(pw * 900 / 1440)
    picture(s, ASSETS / "procedure-check.png", px, TOP, pw)
    add_text(s, px, TOP + ph + 80000, pw, 400000,
             ["Procedure check on the demo with a skipped step."], size=12, color=MUTED)


def chip(s, x, y, w, h, text, fill=PANEL, line=PANEL_2, color=WHITE, size=12, bold=False):
    r = add_rect(s, x, y, w, h, fill, line=line, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    tf = r.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(50000)
    tf.margin_top = tf.margin_bottom = Emu(20000)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    lines = text.split("\n")
    for i, line_text in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = line_text
        run.font.size = Pt(size if i == 0 else size - 2)
        run.font.bold = bold if i == 0 else False
        run.font.color.rgb = color if i == 0 else MUTED
        run.font.name = BODY_FONT
    return r


def arrow(s, x1, y1, x2, y2):
    c = s.shapes.add_connector(1, Emu(x1), Emu(y1), Emu(x2), Emu(y2))
    c.line.color.rgb = CYAN
    c.line.width = Pt(1.5)
    ln = c.line._get_or_add_ln()
    from lxml import etree

    tail = etree.SubElement(ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd")
    tail.set("type", "triangle")
    return c


def slide4(s):
    cw = W - 2 * LM
    # Row 1: browser -> API -> worker
    y1, h1 = TOP, 700000
    bw = 2300000
    gap = (cw - 3 * bw) // 2
    xs = [LM + i * (bw + gap) for i in range(3)]
    chip(s, xs[0], y1, bw, h1, "Next.js frontend\nupload, live progress, results, XR", fill=PANEL_2, line=BLUE, size=15, bold=True)
    chip(s, xs[1], y1, bw, h1, "FastAPI\nREST, SSE, Range-enabled media", fill=PANEL_2, line=BLUE, size=15, bold=True)
    chip(s, xs[2], y1, bw, h1, "Worker pool\nresume, retry, cancel", fill=PANEL_2, line=BLUE, size=15, bold=True)
    arrow(s, xs[0] + bw, y1 + h1 // 2, xs[1], y1 + h1 // 2)
    arrow(s, xs[1] + bw, y1 + h1 // 2, xs[2], y1 + h1 // 2)
    # Row 2: pipeline stages
    add_text(s, LM, y1 + h1 + 230000, cw, 260000, ["PIPELINE, ONE JOB FOLDER PER VIDEO"], size=12, color=CYAN, bold=True)
    stages = ["ingest", "motion", "speech", "understand", "segment", "summarize", "align", "media", "exports"]
    n = len(stages)
    sg = 70000
    sw = (cw - sg * (n - 1)) // n
    y2 = y1 + h1 + 520000
    for i, name in enumerate(stages):
        hl = name == "understand"
        chip(s, LM + i * (sw + sg), y2, sw, 460000, name, fill=BLUE if hl else PANEL,
             line=CYAN if hl else PANEL_2, size=12, bold=hl)
    arrow(s, xs[2] + bw // 2, y1 + h1, xs[2] + bw // 2, y2 - 60000)
    # Row 3: providers and storage
    y3 = y2 + 460000 + 330000
    add_text(s, LM, y3, cw, 260000, ["UNDERSTANDING AND STORAGE"], size=12, color=CYAN, bold=True)
    y4 = y3 + 290000
    items = [
        ("Vision-language provider", "mock, Gemini, OpenAI, Claude, Ollama"),
        ("Text LLM provider", "titles, summary, search answer, step matching"),
        ("Local models", "embeddings for search, optional Whisper"),
        ("SQLite + files + ffmpeg", "state, artifacts, clips, reel"),
    ]
    iw = (cw - 3 * 90000) // 4
    for i, (a, b) in enumerate(items):
        chip(s, LM + i * (iw + 90000), y4, iw, 820000, f"{a}\n{b}", size=13, bold=True)


def slide5(s):
    title = find(s, "Text 2")
    set_text(title, ["TRACK FINAL OUTPUT"])
    pw = 5500000
    ph = int(pw * 2670 / 1440 * 0 + pw * 900 / 1440)
    picture(s, ASSETS / "results.png", LM, TOP, pw)
    add_text(s, LM, TOP + ph + 90000, pw, 500000,
             ["Results page for a processed demo: chapter timeline, step cards, procedure verdict."],
             size=12, color=MUTED)
    rx = LM + pw + 220000
    rw = W - LM - rx
    rh = int(rw * 720 / 1280)
    picture(s, ASSETS / "reel-frame.png", rx, TOP, rw)
    add_text(s, rx, TOP + rh + 60000, rw, 250000, ["Frame from the highlight reel"], size=12, color=MUTED)
    stats = [("6", "steps from a 0:56 video"), ("45 s", "captioned highlight reel"),
             ("1", "skipped step flagged")]
    y = TOP + rh + 360000
    for big, small in stats:
        add_text(s, rx, y, 800000, 400000, [big], size=22, color=CYAN, bold=True, font="Arial Black")
        add_text(s, rx + 850000, y + 20000, rw - 850000, 420000, [small], size=14, anchor=MSO_ANCHOR.TOP)
        y += 520000
    add_text(s, LM, BOTTOM - 130000, W - 2 * LM, 250000,
             ["Demo footage is synthetic and was processed in mock mode, so it shows the pipeline and the product, not model accuracy."],
             size=11, color=AMBER)


def slide6(s):
    cw = W - 2 * LM
    c0 = 1900000
    c1 = (cw - c0) // 2
    rows = [
        ("", "Typical summarisers", "Replay"),
        ("Unit of summary", "Shots, scenes or transcript chunks", "Actions: verb, object, tool"),
        ("Mistakes", "Not detected", "Done, missed or out of order, against your recipe"),
        ("Search", "Keywords in a transcript", "By meaning and words, answer with a timestamp"),
        ("Models", "One vendor, needs a network", "Swappable providers, offline mock mode"),
        ("Output", "A shorter video", "Steps with clips, a captioned reel, PDF, JSON, SRT"),
    ]
    y = TOP
    rh = 560000
    for i, (a, b, c) in enumerate(rows):
        head = i == 0
        if not head:
            add_rect(s, LM, y, cw, rh - 50000, PANEL if i % 2 else BG)
        add_text(s, LM + 120000, y, c0 - 120000, rh - 50000, [a], size=15, color=CYAN, bold=True,
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, LM + c0, y, c1 - 120000, rh - 50000, [b], size=15 if not head else 14,
                 color=MUTED, bold=head, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, LM + c0 + c1, y, c1 - 120000, rh - 50000, [c], size=15 if not head else 14,
                 color=WHITE if not head else CYAN, bold=head, anchor=MSO_ANCHOR.MIDDLE)
        y += rh


def code_box(s, x, y, w, lines, label):
    add_text(s, x, y, w, 260000, [label], size=12, color=CYAN, bold=True)
    h = 330000 * len(lines) + 120000
    add_rect(s, x, y + 290000, w, h, PANEL, line=PANEL_2)
    add_text(s, x + 150000, y + 290000 + 80000, w - 300000, h, lines, size=18, font=MONO_FONT, space_after=4)
    return y + 290000 + h


def slide7(s):
    clear_empty_boxes(s)
    cw = W - 2 * LM
    add_text(s, LM, TOP, cw, 260000, ["DEMO VIDEO"], size=12, color=CYAN, bold=True)
    add_text(s, LM, TOP + 290000, cw, 700000,
             [TEAM["demo_video_url"].replace("https://", ""),
              ("About 3 minutes, 1080p. Synthetic demo footage, mock mode, no voiceover.", {"size": 13, "color": MUTED})],
             size=16, space_after=4)
    half = (cw - 250000) // 2
    y = TOP + 1250000
    code_box(s, LM, y, half, ["make setup", "make demo", "make dev"], "LOCAL, NEEDS PYTHON, UV AND NODE")
    code_box(s, LM + half + 250000, y, half, ["docker compose up --build"], "DOCKER")
    add_text(s, LM + half + 250000, y + 290000 + 330000 + 240000, half, 900000,
             ["Open http://localhost:3000. With no API key the app runs offline on the mock provider."],
             size=14, color=MUTED)
    add_text(s, LM, BOTTOM - 130000, cw, 250000, [f"Source: {TEAM['repo_url'].replace('https://', '')}"], size=13, color=MUTED)


def card(s, x, y, w, h, title, items, size=14):
    add_rect(s, x, y, w, h, PANEL, line=PANEL_2)
    add_rect(s, x, y, w, 45720, CYAN)
    add_text(s, x + 150000, y + 150000, w - 300000, 320000, [title], size=16, color=CYAN, bold=True)
    bullets(s, x + 150000, y + 560000, w - 300000, h - 650000, items, size=size, gap=7)


def slide8(s):
    clear_empty_boxes(s)
    cw = W - 2 * LM
    g = 150000
    w = (cw - 2 * g) // 3
    h = BOTTOM - TOP - 750000
    card(s, LM, TOP, w, h, "XR vision", [
        "Step cards float beside you in WebXR (preview on /xr).",
        "Glasses and headsets already film first-person.",
        "A local Ollama model keeps video on the device.",
    ], size=16)
    card(s, LM + w + g, TOP, w, h, "Evaluation", [
        "3 demos, 18 labelled steps.",
        "Recall 1.00, precision 1.00.",
        "Skipped and swapped steps found, 3 of 3.",
        "Synthetic footage, mock provider: plumbing only, not model accuracy.",
    ], size=16)
    card(s, LM + 2 * (w + g), TOP, w, h, "Roadmap", [
        "Score a real-footage set with a real provider.",
        "Live guidance: show the next step, warn before a skip.",
        "Anchor step cards where each action happened.",
        "Run on a device NPU.",
    ], size=16)


def slide9(s):
    for p in find(s, "Text 9").text_frame.paragraphs:
        p.alignment = PP_ALIGN.CENTER
    bar = find(s, "Text 25")
    set_text(bar, [f"Team {TEAM['team_name']}  |  {TEAM['college']}  |  {TEAM['repo_url'].replace('https://', '')}"], size=11) \
        if bar.text_frame.paragraphs[0].runs else None
    if not bar.text_frame.paragraphs[0].runs:
        p = bar.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = f"Team {TEAM['team_name']}  |  {TEAM['college']}  |  {TEAM['repo_url'].replace('https://', '')}"
        r.font.size = Pt(12)
        r.font.color.rgb = WHITE
        r.font.name = BODY_FONT
        bar.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    add_text(s, 0, 3000000, W, 500000, [f"{TEAM['project']}: {TEAM['tagline'].lower()}"], size=20,
             color=MUTED, align=PP_ALIGN.CENTER)
    add_text(s, 0, 3500000, W, 400000, [", ".join(TEAM["members"])], size=16, color=MUTED, align=PP_ALIGN.CENTER)


def main() -> None:
    prs = Presentation(str(HERE / "template.pptx"))
    builders = [slide1, slide2, slide3, slide4, slide5, slide6, slide7, slide8, slide9]
    for slide, build in zip(prs.slides, builders, strict=True):
        build(slide)
    out = HERE / "Astra_Replay_Submission.pptx"
    prs.save(str(out))
    print("wrote", out)


if __name__ == "__main__":
    main()
