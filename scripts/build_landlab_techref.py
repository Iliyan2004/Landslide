#!/usr/bin/env python3
"""Build docs/LANDLAB_Technical_Reference.{md,html,pdf} from docs/landlab/NN_*.md (the landslide platform only; flooding is a separate product).

Chapter files start with '# Title'; an HTML comment '<!-- part: Name -->' on the first line starts a new Part in the table of contents.
Numbers that come from results are written as {{file.json:path.to.key|fmt}} and are read from docs/validation/*.json when the document is built, so
the text cannot drift from the data; if a result file does not exist yet the placeholder renders as 'pending' (no number is ever invented).
Other placeholders: {{DATE}}, {{TESTS}} (count of unit tests), {{TBL:name}} (generated tables).
No markdown package is installed in the shared venv, so a small converter handles: headings, paragraphs, lists, tables, ``` blocks (formula),
> notes, **bold**, *italic*, `code`.
Usage: ~/flood/venv/bin/python scripts/build_landlab_techref.py [--no-pdf]"""
import datetime as dt, html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CH = sorted((DOCS / "landlab").glob("[0-9][0-9]_*.md"))
VAL = DOCS / "validation"
_cache = {}


def jget(spec):
    f, _, path = spec.partition(":")
    fmt = "g"
    if "|" in path:
        path, fmt = path.split("|", 1)
    p = VAL / f
    if not p.exists():
        return "pending"
    d = _cache.setdefault(f, json.loads(p.read_text()))
    try:
        for k in path.split("."):
            d = d[int(k)] if isinstance(d, list) else d[k]
    except (KeyError, IndexError, ValueError, TypeError):
        return "pending"
    if isinstance(d, (int, float)):
        return {"g": f"{d:.4g}", "0": f"{d:,.0f}", "1": f"{d:,.1f}", "2": f"{d:.2f}", "3": f"{d:.3f}", "pct": f"{100*d:.0f}%"}.get(fmt, f"{d:.4g}").replace("nan", "n/a")
    return str(d)


def tests_count():
    n = 0
    for f in (ROOT / "backend/tests").glob("test_*.py"):
        n += len(re.findall(r"^\s+def test_", f.read_text(), re.M))
    return str(n)


SLUGS = {}


def fill(t):
    t = re.sub(r"\{\{ch:([a-z0-9_]+)\}\}", lambda m: str(SLUGS.get(m.group(1), "?")), t)
    t = re.sub(r"\{\{([A-Za-z0-9_\-]+\.json:[^}]+)\}\}", lambda m: jget(m.group(1)), t)
    return t.replace("{{DATE}}", dt.date.today().strftime("%d %B %Y")).replace("{{TESTS}}", tests_count())


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return s.replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;").replace("&amp;nbsp;", "&nbsp;").replace("&amp;times;", "&times;").replace("&amp;deg;", "&deg;")


def md(text):
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append('<div class="formula">' + html.escape("\n".join(buf)) + "</div>"); i = j + 1; continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            align = ["num" if c.strip().endswith(":") else "" for c in lines[i + 1].strip().strip("|").split("|")]
            rows = []; j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")]); j += 1
            th = "".join(f'<th class="{a}">{inline(h)}</th>' for h, a in zip(head, align))
            tb = "".join("<tr>" + "".join(f'<td class="{a}">{inline(c)}</td>' for c, a in zip(r, align)) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"); i = j; continue
        if ln.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip()); i += 1
            out.append('<div class="note">' + inline(" ".join(buf)) + "</div>"); continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            lvl = len(m.group(1)); out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if re.match(r"^\s*([-*]|\d+\.) ", ln):
            ordered = bool(re.match(r"^\s*\d+\.", ln)); items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i])); i += 1
                while i < len(lines) and lines[i].startswith("  ") and not re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                    items[-1] += " " + lines[i].strip(); i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>"); continue
        if not ln.strip():
            i += 1; continue
        buf = [ln]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3} |```|\||>|\s*([-*]|\d+\.) )", lines[i]):
            buf.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")
    return "\n".join(out)


CSS = """@page{size:A4;margin:20mm 18mm;@bottom-right{content:"LANDLAB Technical Reference \\2022  Page " counter(page);font:8.5pt "DejaVu Sans",sans-serif;color:#7a5a3a}}
@page cover{margin:0;@bottom-right{content:none}}
:root{--c1:#7a4a12;--c2:#b8741e;--ink:#1f2326;--muted:#5d666b;--rule:#d9d2c7;--tint:#f6f1e8;--amber-bg:#fff4dc}
html{font-family:"DejaVu Sans","Liberation Sans",sans-serif;font-size:9.6pt;line-height:1.5;color:var(--ink)}body{margin:0}
.cover{page:cover;height:297mm;box-sizing:border-box;padding:62mm 24mm 24mm;background:linear-gradient(160deg,#3d2406 0%,#7a4a12 55%,#b8741e 100%);color:#fff}
.cover .eyebrow{letter-spacing:.32em;font-size:9pt;text-transform:uppercase;opacity:.85}.cover h1{font-size:46pt;margin:18mm 0 4mm;letter-spacing:.04em}
.cover .expand{font-size:13pt;max-width:140mm;opacity:.95}.cover .lede{font-size:12pt;margin-top:10mm;max-width:140mm}.cover .scope{margin-top:26mm;font-size:10pt;max-width:150mm;line-height:1.6;opacity:.92}.cover .date{margin-top:10mm;font-size:10pt;opacity:.85}
h1.chapter{page-break-before:always;font-size:19pt;color:var(--c1);margin:0 0 4mm;border-bottom:2px solid var(--c1);padding-bottom:2mm}
h2{font-size:11.5pt;color:var(--c1);margin:6mm 0 2mm;padding-left:3mm;border-left:3px solid var(--c2);page-break-after:avoid}h3{font-size:10pt;margin:4mm 0 1.5mm;page-break-after:avoid}
p{margin:0 0 2.4mm}ul,ol{margin:0 0 2.6mm;padding-left:6mm}li{margin-bottom:1.2mm}
code{font-family:"DejaVu Sans Mono",monospace;font-size:8.4pt;background:var(--tint);padding:0 1mm;border-radius:1mm}
.formula{font-family:"DejaVu Sans Mono",monospace;font-size:8.8pt;background:var(--tint);border-left:3px solid var(--c2);padding:2.5mm 4mm;margin:2mm 0 3mm;white-space:pre-wrap;page-break-inside:avoid}
table{width:100%;border-collapse:collapse;margin:2mm 0 4mm;font-size:8.5pt}th{text-align:left;background:var(--c1);color:#fff;padding:1.6mm 2mm;font-size:8.1pt;text-transform:uppercase;letter-spacing:.03em}
td{padding:1.5mm 2mm;border-bottom:1px solid var(--rule);vertical-align:top}tr:nth-child(even) td{background:#faf7f1}tr{page-break-inside:avoid}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.note{background:var(--amber-bg);border-left:3px solid #d39a2a;padding:2.5mm 4mm;margin:2mm 0 4mm;color:#3d2c00;page-break-inside:avoid}
.toc{page-break-before:always}.toc h1{font-size:19pt;color:var(--c1);border-bottom:2px solid var(--c1);padding-bottom:2mm;margin:0 0 4mm}.toc .part{font-weight:bold;color:var(--c1);margin:3.5mm 0 1mm}.toc .item{margin:0 0 .8mm 5mm}
.toc .item a{color:var(--ink);text-decoration:none}.toc .item a::after{content:leader('.') target-counter(attr(href),page);color:var(--muted)}"""


def build(pdf=True):
    parts, chapters = [], []
    SLUGS.clear()
    SLUGS.update({f.stem[3:]: i + 1 for i, f in enumerate(CH)})
    for f in CH:
        t = fill(f.read_text())
        pm = re.match(r"<!-- part: (.*?) -->\n", t)
        part = pm.group(1) if pm else None
        if pm:
            t = t[pm.end():]
        title = re.match(r"# (.*)", t).group(1)
        chapters.append((part, title, t))
    body, toc, n, cur = [], [], 0, None
    for part, title, t in chapters:
        n += 1
        if part and part != cur:
            toc.append(f'<div class="part">{html.escape(part)}</div>'); cur = part
        toc.append(f'<div class="item"><a href="#ch{n}">{n}. {html.escape(title)}</a></div>')
        text = re.sub(r"^# .*\n", "", t, count=1)
        body.append(f'<h1 class="chapter" id="ch{n}">{n}. {inline(title)}</h1>\n' + md(text))
    cover = (f'<div class="cover"><div class="eyebrow">Technical Reference</div><h1>LANDLAB</h1><div class="expand">Landslide hazard, runout and impact modelling for Pakistan</div>'
             f'<div class="lede">How every number is produced: data, physics, solver, GPU implementation, calibration and validation, and what is not known.</div>'
             f'<div class="scope">Scope: landslides only (rain-, earthquake-triggered; debris flow, earth flow, shallow slides). Flooding is a separate product (SAILAB) and is not part of, or coupled to, this system.</div>'
             f'<div class="date">{dt.date.today():%d %B %Y} &middot; {len(chapters)} chapters &middot; {tests_count()} unit tests</div></div>')
    toc_html = '<div class="toc"><h1>Contents</h1>' + "".join(toc) + "</div>"
    doc = f'<!doctype html><html><head><meta charset="utf-8"><title>LANDLAB Technical Reference</title><style>{CSS}</style></head><body>{cover}{toc_html}{"".join(body)}</body></html>'
    (DOCS / "LANDLAB_Technical_Reference.html").write_text(doc, encoding="utf-8")
    (DOCS / "LANDLAB_Technical_Reference.md").write_text("\n\n".join(re.sub(r"^# ", f"# {i+1}. ", t, count=1) for i, (_, _, t) in enumerate(chapters)), encoding="utf-8")
    print(f"chapters {len(chapters)}  html {len(doc)//1024} KB", flush=True)
    if pdf:
        import weasyprint
        weasyprint.HTML(string=doc).write_pdf(str(DOCS / "LANDLAB_Technical_Reference.pdf"))
        print("pdf", (DOCS / "LANDLAB_Technical_Reference.pdf").stat().st_size // 1024, "KB", flush=True)


if __name__ == "__main__":
    build(pdf="--no-pdf" not in sys.argv)
