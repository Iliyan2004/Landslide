"""Run report in SAILAB's format (flood_model.build_report_html): masthead with the model name and run meta, a summary tile grid, map plates with captions and a
legend row, hover charts, a run-configuration table and a footer, with SAILAB's light and dark theme. Self-contained (no network fonts, images inline) so a browser and
weasyprint render it the same way. Reads only the run folder (summary.json, manifest.json, arrays.npz)."""
from __future__ import annotations
import base64, io, json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import numpy as np
from PIL import Image
from . import render

MODEL_NAME = "LANDLAB"
MODEL_TAGLINE = "From slope to risk, modelled."
ACCENT_LIGHT, ACCENT_DARK = "#0E7A8C", "#5FD3E8"        # SAILAB's accent colours
CSS = """
:root { --page:#F3F6F8; --surface:#FFFFFF; --surface-2:#E9F1F3; --ink:#142430; --ink-2:#46606B; --muted:#7C929B; --line:#D7E2E5; --accent:%(al)s; --accent-soft:#E3F2F4; --paper:#FCFDFD; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --page:#0B1417; --surface:#101B1F; --surface-2:#142327; --ink:#E7EEF0; --ink-2:#A9BEC4; --muted:#6E848B; --line:#22343A; --accent:%(ad)s; --accent-soft:#10333A; --paper:#F4F6F5; color-scheme:dark; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font-family:"Public Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; -webkit-font-smoothing:antialiased; }
.wrap { max-width:1180px; margin:0 auto; padding:28px 24px 64px; }
.masthead { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; flex-wrap:wrap; border-bottom:2px solid var(--ink); padding-bottom:14px; margin-bottom:22px; }
.brand { display:flex; align-items:baseline; gap:10px; }
.brand-mark { font-family:"Barlow Condensed","Arial Narrow",sans-serif; font-weight:700; font-size:34px; letter-spacing:.01em; text-transform:uppercase; color:var(--ink); }
.brand-tag { color:var(--muted); font-size:13px; max-width:30ch; }
.run-meta { font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:12px; color:var(--ink-2); text-align:right; line-height:1.7; }
.run-meta b { color:var(--ink); }
h2.section-title { font-family:"Barlow Condensed","Arial Narrow",sans-serif; font-weight:600; text-transform:uppercase; letter-spacing:.06em; font-size:15px; color:var(--ink-2); margin:40px 0 14px; padding-bottom:8px; border-bottom:1px solid var(--line); }
.tiles { display:flex; flex-wrap:wrap; gap:1px; background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.tile { background:var(--surface); padding:16px 18px; flex:1 1 170px; min-width:150px; }
.tile-label { font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.tile-value { font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:24px; font-weight:500; color:var(--ink); margin-top:4px; font-variant-numeric:tabular-nums; }
.tile-sub { font-size:11.5px; color:var(--muted); margin-top:3px; }
.maps-grid { font-size:0; }
.plate { display:inline-block; vertical-align:top; width:48.6%%; margin:0 1.2%% 18px 0; page-break-inside:avoid; font-size:13px; background:var(--paper); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.plate img { display:block; width:100%%; height:auto; }
.plate-cap { padding:10px 14px; font-size:12.5px; color:#46606B; background:var(--paper); border-top:1px solid #e3e9ea; }
.plate-cap b { color:#142430; }
.legend-row { display:flex; flex-wrap:wrap; gap:14px; margin:12px 0 4px; }
.legend-chip { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--ink-2); background:var(--surface-2); border:1px solid var(--line); border-radius:999px; padding:4px 10px 4px 8px; }
.legend-chip .swatch { width:10px; height:10px; border-radius:3px; display:inline-block; }
.legend-pct { font-family:"IBM Plex Mono", ui-monospace, monospace; color:var(--ink); margin-left:2px; }
.charts-grid { font-size:0; }
@media (max-width:640px) { .plate, .chart-card { width:100%%; margin-right:0; } }
@page { size:A4; margin:12mm; }
.chart-card { display:inline-block; vertical-align:top; width:48.6%%; margin:0 1.2%% 16px 0; page-break-inside:avoid; font-size:13px; background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px 8px; }
.chart-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; }
.chart-title { font-size:13px; font-weight:500; color:var(--ink); }
.chart-unit { font-size:11px; color:var(--muted); font-family:"IBM Plex Mono", ui-monospace, monospace; }
.chart-svg-wrap { position:relative; }
.spark-chart { width:100%%; height:auto; display:block; overflow:visible; }
.gridline { stroke:var(--line); stroke-width:1; }
.axis-label { font-size:9px; fill:var(--muted); font-family:"IBM Plex Mono", ui-monospace, monospace; }
.area-fill { opacity:.14; } .line-path { fill:none; stroke-width:2; } .end-dot { stroke:var(--surface); stroke-width:1.5; }
.crosshair-line { stroke:var(--muted); stroke-width:1; stroke-dasharray:2 2; } .crosshair-dot { stroke:var(--surface); stroke-width:1.5; } .hover-capture { cursor:crosshair; }
.chart-tooltip { position:absolute; pointer-events:none; opacity:0; transition:opacity .08s; background:var(--ink); color:var(--paper); font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:11px; padding:4px 7px; border-radius:5px; white-space:nowrap; transform:translate(-50%%, -130%%); z-index:5; }
table.appendix { width:100%%; border-collapse:collapse; font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:12.5px; }
table.appendix td { padding:5px 10px; border-bottom:1px solid var(--line); color:var(--ink-2); }
table.appendix td:first-child { color:var(--muted); width:40%%; } table.appendix td:last-child { color:var(--ink); }
ul.notes { margin:0; padding-left:18px; color:var(--ink-2); font-size:12.5px; line-height:1.65; }
.banner { margin-top:14px; padding:10px 14px; border:1px solid var(--line); border-left:3px solid var(--accent); background:var(--accent-soft); border-radius:6px; font-size:12.5px; color:var(--ink-2); }
footer { margin-top:44px; padding-top:16px; border-top:1px solid var(--line); font-size:12px; color:var(--muted); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }
""" % {"al": ACCENT_LIGHT, "ad": ACCENT_DARK}


def _fmt(v, d=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:,.{d}f}"


def _money(v):
    v = float(v or 0); sg = "-" if v < 0 else ""; v = abs(v)
    return "PKR " + sg + (f"{v / 1e9:,.2f} bn" if v >= 1e9 else f"{v / 1e6:,.1f} M")


def _tile(label, value, sub=""):
    return f'<div class="tile"><div class="tile-label">{escape(label)}</div><div class="tile-value">{value}</div><div class="tile-sub">{escape(sub)}</div></div>'


def _chart(cid, title, unit, t, y, color, xunit="h", width=460, height=200, yd=1):
    t, y = np.asarray(t, float), np.asarray(y, float)
    if len(t) < 2 or not np.isfinite(y).any():
        return ""
    ml, mr, mt, mb = 44, 14, 14, 26; x0, x1 = float(t.min()), float(t.max()); y0, y1 = 0.0, max(float(np.nanmax(y)) * 1.15, 1e-6)
    sx = lambda v: ml + (v - x0) / max(x1 - x0, 1e-9) * (width - ml - mr); sy = lambda v: (height - mb) - (v - y0) / max(y1 - y0, 1e-9) * (height - mt - mb)
    pts = [(sx(a), sy(b)) for a, b in zip(t, y)]; line = "M " + " L ".join(f"{x:.2f},{v:.2f}" for x, v in pts)
    area = line + f" L {pts[-1][0]:.2f},{height - mb} L {pts[0][0]:.2f},{height - mb} Z"
    grid = "".join(f'<line x1="{ml}" y1="{sy(y0 + f * (y1 - y0)):.1f}" x2="{width - mr}" y2="{sy(y0 + f * (y1 - y0)):.1f}" class="gridline"/>'
                   f'<text x="{ml - 6}" y="{sy(y0 + f * (y1 - y0)) + 3:.1f}" class="axis-label" text-anchor="end">{y0 + f * (y1 - y0):.{yd}f}</text>' for f in (0, .5, 1))
    xt = "".join(f'<text x="{sx(x0 + f * (x1 - x0)):.1f}" y="{height - 6}" class="axis-label" text-anchor="middle">{x0 + f * (x1 - x0):.1f}{xunit}</text>' for f in (0, .5, 1))
    pj = json.dumps([[round(float(a), 3), round(float(b), 4)] for a, b in zip(t, y)])
    return f"""<div class="chart-card"><div class="chart-head"><span class="chart-title">{escape(title)}</span><span class="chart-unit">{escape(unit)}</span></div>
<div class="chart-svg-wrap"><svg class="spark-chart" id="{cid}" viewBox="0 0 {width} {height}" data-x0="{x0}" data-x1="{x1}" data-y0="{y0}" data-y1="{y1}" data-ml="{ml}" data-mr="{mr}" data-mt="{mt}" data-mb="{mb}"
data-w="{width}" data-h="{height}" data-yd="{yd}" data-unit="{escape(unit)}" data-xu="{xunit}" preserveAspectRatio="none">{grid}<path d="{area}" class="area-fill" style="fill:{color}"/><path d="{line}" class="line-path" style="stroke:{color}"/>
<circle cx="{pts[-1][0]:.2f}" cy="{pts[-1][1]:.2f}" r="3.2" class="end-dot" style="fill:{color}"/>{xt}<g class="crosshair" style="display:none"><line class="crosshair-line" x1="0" y1="{mt}" x2="0" y2="{height - mb}"/><circle class="crosshair-dot" r="3.6" style="fill:{color}"/></g>
<rect class="hover-capture" x="{ml}" y="{mt}" width="{width - ml - mr}" height="{height - mt - mb}" fill="transparent" data-points='{pj}'/></svg><div class="chart-tooltip" data-for="{cid}"></div></div></div>"""


HOVER_JS = """<script>(function(){document.querySelectorAll('.spark-chart').forEach(function(svg){var rect=svg.querySelector('.hover-capture'),cross=svg.querySelector('.crosshair'),line=svg.querySelector('.crosshair-line'),dot=svg.querySelector('.crosshair-dot'),tip=document.querySelector('.chart-tooltip[data-for="'+svg.id+'"]'),pts=JSON.parse(rect.getAttribute('data-points')),x0=+svg.dataset.x0,x1=+svg.dataset.x1,y0=+svg.dataset.y0,y1=+svg.dataset.y1,ml=+svg.dataset.ml,mr=+svg.dataset.mr,mt=+svg.dataset.mt,mb=+svg.dataset.mb,w=+svg.dataset.w,h=+svg.dataset.h,yd=+svg.dataset.yd,unit=svg.dataset.unit,xu=svg.dataset.xu;
function sx(v){return ml+(v-x0)/Math.max(x1-x0,1e-9)*(w-ml-mr)}function sy(v){return(h-mb)-(v-y0)/Math.max(y1-y0,1e-9)*(h-mt-mb)}
function move(e){var b=svg.getBoundingClientRect(),px=(e.clientX-b.left)/b.width*w,f=Math.min(1,Math.max(0,(px-ml)/(w-ml-mr))),tv=x0+f*(x1-x0),i=0,best=1e18;for(var k=0;k<pts.length;k++){var d=Math.abs(pts[k][0]-tv);if(d<best){best=d;i=k}}var p=pts[i],xx=sx(p[0]),yy=sy(p[1]);cross.style.display='block';line.setAttribute('x1',xx);line.setAttribute('x2',xx);dot.setAttribute('cx',xx);dot.setAttribute('cy',yy);tip.style.left=(xx/w*b.width)+'px';tip.style.top=(yy/h*b.height)+'px';tip.textContent=p[0].toFixed(1)+' '+xu+' — '+p[1].toFixed(yd)+' '+unit;tip.style.opacity=1}
rect.addEventListener('mousemove',move);rect.addEventListener('mouseleave',function(){cross.style.display='none';tip.style.opacity=0})})})();</script>"""


def _hillshade(dem, res):
    z = np.where(np.isfinite(dem), dem, np.nanmedian(dem)); gy, gx = np.gradient(z, res)
    az, alt = np.deg2rad(315), np.deg2rad(40); slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


def _plate(a, ramp, dem, res, mask_below=None, max_px=900):
    """Map image: the layer in its colour ramp over a hillshade, in the analysis grid (north up). Returns base64 PNG."""
    a = np.array(a, float)
    if mask_below is not None:
        a = np.where(a > mask_below, a, np.nan)
    hs = (0.55 + 0.45 * _hillshade(dem, res)) * 235; base = np.stack([hs, hs, hs * 0.99], -1).astype(np.float32)
    rgba = render.colorize(a, ramp, alpha=0.88).astype(np.float32); al = rgba[..., 3:4] / 255.0
    img = (base * (1 - al) + rgba[..., :3] * al).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(img); s = max(1.0, max(im.size) / max_px)
    if s > 1:
        im = im.resize((int(im.width / s), int(im.height / s)), Image.BILINEAR)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def _legend(ramp, label, lo, hi):
    stops = render.RAMPS[ramp][0]; xs = ",".join(f"rgb({int(c[0])},{int(c[1])},{int(c[2])})" for _, c in stops)
    return f'<div class="legend-chip"><span class="swatch" style="width:70px;background:linear-gradient(90deg,{xs})"></span>{escape(label)} <span class="legend-pct">{lo} – {hi}</span></div>'


def build_html(rid, runs_root):
    rdir = Path(runs_root) / rid; d = json.loads((rdir / "summary.json").read_text()); s = d["summary"]
    man = json.loads((rdir / "manifest.json").read_text()) if (rdir / "manifest.json").exists() else {}
    params = man.get("params") or {}; z = np.load(rdir / "arrays.npz") if (rdir / "arrays.npz").exists() else None
    fl, ex, tr, qk = s.get("flow") or {}, s.get("exposure") or {}, s.get("trigger") or {}, s.get("quake") or {}
    mode = s.get("mode", "rain"); res = float(s.get("resolution_m") or 30.0); tiles, plates, legend, charts = [], [], [], []
    dem = z["dem"] if z is not None and "dem" in z.files else None
    tiles = [_tile("Failing area", _fmt(tr.get("failing_area_km2"), 3) + " km²", f"{_fmt(100 * (tr.get('failing_frac_of_area') or 0), 1)} % of the area"),
             _tile("Released volume", _fmt((fl.get("released_volume_m3") or 0) / 1e6, 2) + " Mm³", f"{_fmt(fl.get('entrained_volume_m3'), 0)} m³ entrained"),
             _tile("Impacted area", _fmt(fl.get("impacted_area_km2"), 3) + " km²", "flow depth over 0.3 m"),
             _tile("Max depth", _fmt(fl.get("max_depth_m"), 1) + " m", f"max speed {_fmt(fl.get('max_speed_ms'), 1)} m/s"),
             _tile("Max runout", _fmt(fl.get("max_runout_m"), 0) + " m", "from the source cells"),
             _tile("Buildings DS ≥ 3", _fmt(ex.get("buildings_ds_ge3"), 0), f"{_fmt(ex.get('buildings_damaged_ds_ge1'), 0)} damaged of {_fmt(ex.get('buildings_in_aoi'), 0)}"),
             _tile("Direct loss", _money(ex.get("direct_loss_pkr")), "structure + contents + crops"),
             _tile("Roads blocked", _fmt(ex.get("road_blocked_km"), 2) + " km", f"of {_fmt(ex.get('road_length_km'), 1)} km"),
             _tile("People in impacted cells", _fmt(ex.get("population_in_impacted_cells"), 0), "population raster")]
    if qk:
        tiles.insert(1, _tile("Peak PGA", _fmt(qk.get("pga_g_max"), 2) + " g", f"M {qk.get('magnitude')} · rupture {_fmt(qk.get('rupture_km'), 0)} km"))
    if (ex.get("access") or {}).get("points"):
        a = ex["access"]; tiles.append(_tile("Cut off from roads", _fmt(a.get("cut_off"), 0), f"of {_fmt(a.get('points'), 0)} buildings and facilities"))
    layers = [("hmax", "hmax", "Maximum flow depth", "Peak debris depth per cell over the run, m.", 0.05), ("deposit", "deposit", "Net deposit", "Thickness left on the ground after the flow stopped, m.", 0.05),
              ("t_fail_h", "t_fail_h", "Failure time", "Hours from the start of the storm to the first failure of each cell.", None), ("fs_min", "min_fs_p50", "Minimum factor of safety", "Lowest FS reached; below 1 the slope fails.", None),
              ("pga_g", "pga_g", "Peak ground acceleration", "Mean horizontal PGA from the ground-motion model, g.", None)]
    if z is not None and dem is not None:
        for key, ramp, title, cap, thr in layers:
            if key in z.files and np.isfinite(z[key]).any():
                v = z[key]; ok = np.isfinite(v) & ((v > thr) if thr is not None else True)
                if ok.any():
                    plates.append(f'<div class="plate"><img src="data:image/png;base64,{_plate(v, ramp, dem, res, thr)}" alt="{escape(title)}"><div class="plate-cap"><b>{escape(title)}.</b> {escape(cap)}</div></div>')
                    lo, hi = np.nanpercentile(v[ok], [1, 99])
                    if hi <= lo:
                        plates.pop(); continue
                    legend.append(_legend(ramp, title, f"{lo:.3g}", f"{hi:.3g}"))
    rain = (params.get("rain") or {})
    if rain.get("times_h") and rain.get("rate_mm_h"):
        charts.append(_chart("c-rain", "Rainfall intensity", "mm / h", rain["times_h"], rain["rate_mm_h"], ACCENT_LIGHT, "h", yd=0))
    fct = tr.get("failed_cells_vs_time")
    if fct:
        charts.append(_chart("c-fail", "Failed area", "km²", fct["t_h"], np.array(fct["cells"]) * res * res / 1e6, ACCENT_LIGHT, "h", yd=3))
    prm = tr.get("params") or {}
    cfg = [("Run", rid), ("Mode", mode), ("Model version", f"{MODEL_NAME} {man.get('model_version', '')}"), ("Area", f"{_fmt(s.get('area_km2'), 2)} km²"), ("Grid", f"{s.get('grid')} @ {res:.0f} m"), ("Solver backend", s.get("backend") or "—")]
    cfg += [("Strength preset / quantile", f"{params.get('strength_preset', '—')} / {params.get('strength_quantile', '—')}"), ("Soil texture", params.get("texture", "—")),
            ("Cohesion · friction · depth", f"{prm.get('effective_cohesion', '—')} Pa · {prm.get('friction_angle', '—')}° · {_fmt(tr.get('soil_depth_mean_m'), 2)} m mean"),
            ("Failure type (mu, xi)", f"{fl.get('failure_type', '—')} ({fl.get('mu', '—')}, {fl.get('xi', '—')})"), ("Antecedent wetness", json.dumps(tr.get("antecedent")) if tr.get("antecedent") else "off"),
            ("Spatial ground", json.dumps(tr.get("spatial_ground")) if tr.get("spatial_ground") else "off"), ("Ensemble", (f"{(s.get('ensemble') or {}).get('members')} members" if s.get("ensemble") else "off")),
            ("Mass check", f"{_fmt(fl.get('mass_check_m3'), 1)} m³ (should be ≈ 0)")]
    if qk:
        cfg.append(("Ground motion", qk.get("model", "—")))
    cfg.append(("Elapsed", f"{_fmt(s.get('elapsed_total_s') or s.get('elapsed_s'), 1)} s"))
    cfg_rows = "".join(f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>" for k, v in cfg)
    notes = "".join(f"<li>{escape(w)}</li>" for w in d.get("warnings", []))
    if ex.get("loss_note"):
        notes += f"<li>{escape(ex['loss_note'])}</li>"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = f"<div><b>Mode</b> {escape(mode)}</div><div><b>Domain</b> {s.get('grid', ['?', '?'])[1] if s.get('grid') else '?'}&times;{s.get('grid', ['?', '?'])[0] if s.get('grid') else '?'} cells @ {res:.0f} m</div><div><b>Solver</b> Voellmy local-inertial · {escape(str(s.get('backend') or ''))}</div>"
    sec = lambda title, inner: f'<h2 class="section-title">{title}</h2>{inner}' if inner else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{MODEL_NAME} report {escape(rid)}</title><style>{CSS}</style></head><body><div class="wrap">
<div class="masthead"><div class="brand"><span class="brand-mark">{MODEL_NAME}</span><span class="brand-tag">{MODEL_TAGLINE}</span></div><div class="run-meta">{meta}</div></div>
<div class="banner">Screening-grade decision support. Not for engineering design or evacuation orders.</div>
{sec("Summary", f'<div class="tiles">{"".join(tiles)}</div>')}
{sec("Failure, runout &amp; hazard maps", f'<div class="maps-grid">{"".join(plates)}</div><div class="legend-row">{"".join(legend)}</div>' if plates else "")}
{sec("Storm &amp; failure evolution", f'<div class="charts-grid">{"".join(charts)}</div>' if charts else "")}
{sec("Run configuration", f'<table class="appendix">{cfg_rows}</table>')}
{sec("Assumptions &amp; warnings", f'<ul class="notes">{notes}</ul>' if notes else "")}
<footer><span>{MODEL_NAME} &middot; infinite-slope + Green-Ampt trigger, Voellmy local-inertial runout (Bates et al. 2010)</span><span>Generated {when}</span></footer></div>{HOVER_JS}</body></html>"""


# ------------------------------------------------------------------ compare and batch reports in SAILAB's band format (fis_app.REPORT_CSS)
BAND_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; color: #17242A; background: #F4F8F9; }
.report-band { background: linear-gradient(120deg, #0B2A2E 0%, #114044 55%, #0E3438 100%); color: #EAF6F6; padding: 26px 36px 22px; }
.report-band h1 { margin: 0; font-size: 23px; font-weight: 700; letter-spacing: 0.02em; }
.report-band .tagline { color: #9FE0DC; margin: 4px 0 0; font-size: 12.5px; letter-spacing: 0.01em; }
.report-body { max-width: 900px; margin: 0 auto; padding: 28px 36px 40px; background: #FFFFFF; }
h2 { font-size: 15px; color: #0E4448; margin: 30px 0 10px; padding-left: 11px; border-left: 3px solid #1FB6AE; letter-spacing: 0.01em; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 4px; font-size: 13px; }
th, td { text-align: left; padding: 8px 11px; border-bottom: 1px solid #E1E8E9; }
th { color: #4C6367; font-weight: 600; background: #EEF5F5; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.03em; }
tr:nth-child(even) td { background: #FAFCFC; }
.legend span { display: inline-block; width: 11px; height: 11px; margin-right: 5px; vertical-align: middle; border-radius: 3px; }
img { max-width: 100%; border: 1px solid #E1E8E9; border-radius: 8px; margin: 10px 0; display: block; }
.note { color: #6C8286; font-size: 12px; line-height: 1.6; margin-top: 14px; }
"""


def _band_page(title, inner):
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{escape(MODEL_NAME)} {escape(title)}</title><style>{BAND_CSS}</style></head><body>'
            f'<div class="report-band"><h1>{MODEL_NAME} &mdash; {escape(title)}</h1><p class="tagline">{MODEL_TAGLINE}</p></div><div class="report-body">{inner}</div></body></html>')


def _png_b64(rgb, max_px=900):
    im = Image.fromarray(rgb); s = max(1.0, max(im.size) / max_px)
    if s > 1:
        im = im.resize((int(im.width / s), int(im.height / s)), Image.NEAREST)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def _load_run(rid, runs_root):
    r = Path(runs_root) / rid; d = json.loads((r / "summary.json").read_text()); z = np.load(r / "arrays.npz") if (r / "arrays.npz").exists() else None
    man = json.loads((r / "manifest.json").read_text()) if (r / "manifest.json").exists() else {}
    return d["summary"], z, man


def _scenario(s, man):
    p = man.get("params") or {}; q = s.get("quake") or {}; rn = s.get("rain") or {}
    if q:
        return f"M {q.get('magnitude')} earthquake"
    return f"{_fmt(rn.get('total_mm'), 0)} mm rain, peak {_fmt(rn.get('peak_mm_h'), 0)} mm/h" + (f" · {p.get('strength_preset')}" if p.get("strength_preset") else "")


def compare_html(a_id, b_id, runs_root):
    sa, za, ma = _load_run(a_id, runs_root); sb, zb, mb = _load_run(b_id, runs_root)
    if za is None or zb is None or za["hmax"].shape != zb["hmax"].shape:
        raise ValueError("both runs need physics results on the same area and grid (same polygon and resolution)")
    cell = (ma["grid"]["resolution_m"] ** 2) / 1e6; ha, hb = np.nan_to_num(za["hmax"]), np.nan_to_num(zb["hmax"]); wa, wb = ha > 0.3, hb > 0.3
    valid = np.isfinite(za["hmax"]) | np.isfinite(zb["hmax"]); dem = za["dem"]; hs = (0.55 + 0.45 * _hillshade(dem, ma["grid"]["resolution_m"])) * 235
    img = np.stack([hs, hs, hs], -1).astype(np.uint8); img[wa & ~wb] = (46, 204, 113); img[wb & ~wa] = (200, 30, 30); img[wa & wb] = (63, 140, 224)
    ea, eb = sa.get("exposure") or {}, sb.get("exposure") or {}; fa, fb = sa.get("flow") or {}, sb.get("flow") or {}; ta, tb = sa.get("trigger") or {}, sb.get("trigger") or {}
    row = lambda label, x, y: f"<tr><td>{label}</td><td>{x}</td><td>{y}</td></tr>"
    loss_a, loss_b = ea.get("direct_loss_pkr"), eb.get("direct_loss_pkr")
    loss_rows = row("Direct loss", _money(loss_a), _money(loss_b)) + (f"<tr><td>Loss difference (B&minus;A)</td><td colspan='2'>{_money((loss_b or 0) - (loss_a or 0))}</td></tr>" if loss_a is not None and loss_b is not None else "")
    inner = (f"<table><tr><th></th><th>Run A ({escape(a_id[:8])})</th><th>Run B ({escape(b_id[:8])})</th></tr>"
             + row("Scenario", escape(_scenario(sa, ma)), escape(_scenario(sb, mb))) + row("Failing area", f"{_fmt(ta.get('failing_area_km2'), 3)} km&sup2;", f"{_fmt(tb.get('failing_area_km2'), 3)} km&sup2;")
             + row("Released volume", f"{_fmt(fa.get('released_volume_m3'), 0)} m&sup3;", f"{_fmt(fb.get('released_volume_m3'), 0)} m&sup3;") + row("Impacted area", f"{_fmt(fa.get('impacted_area_km2'), 3)} km&sup2;", f"{_fmt(fb.get('impacted_area_km2'), 3)} km&sup2;")
             + row("Max depth", f"{_fmt(fa.get('max_depth_m'), 1)} m", f"{_fmt(fb.get('max_depth_m'), 1)} m") + row("Buildings DS &ge; 3", _fmt(ea.get("buildings_ds_ge3"), 0), _fmt(eb.get("buildings_ds_ge3"), 0)) + loss_rows + "</table>"
             f"<h2>Cell-by-cell comparison</h2><table><tr><td>Only run A impacted</td><td>{_fmt((wa & ~wb).sum() * cell, 4)} km&sup2; ({int((wa & ~wb).sum()):,} cells)</td></tr>"
             f"<tr><td>Only run B impacted</td><td>{_fmt((wb & ~wa).sum() * cell, 4)} km&sup2; ({int((wb & ~wa).sum()):,} cells)</td></tr><tr><td>Both impacted</td><td>{_fmt((wa & wb).sum() * cell, 4)} km&sup2; ({int((wa & wb).sum()):,} cells)</td></tr>"
             f"<tr><td>Mean depth change (B&minus;A) where either is impacted</td><td>{_fmt(float((hb - ha)[wa | wb].mean()) if (wa | wb).any() else 0.0, 2)} m</td></tr></table>"
             '<p class="legend"><span style="background:#2ecc71;"></span>Only run A &nbsp;<span style="background:#c81e1e;"></span>Only run B &nbsp;<span style="background:#3f8ce0;"></span>Both &nbsp;<span style="background:#e8ecec;"></span>Neither</p>'
             f'<img src="data:image/png;base64,{_png_b64(img)}" alt="Run difference map"><p class="note">Cell-by-cell comparison of each run\'s maximum flow depth (impacted = depth over 0.3 m); only valid for two runs on the same area and grid.</p>')
    return _band_page("Run Comparison", inner)


def batch_html(ids, runs_root):
    rows, labels, fa, imp = "", [], [], []
    for rid in ids:
        if not (Path(runs_root) / rid / "summary.json").exists():
            continue
        s, _z, man = _load_run(rid, runs_root); ex, fl, tr = s.get("exposure") or {}, s.get("flow") or {}, s.get("trigger") or {}
        rows += (f"<tr><td>{escape(rid[:8])}</td><td>{escape(_scenario(s, man))}</td><td>{_fmt(tr.get('failing_area_km2'), 2)}</td><td>{_fmt(fl.get('released_volume_m3'), 0)}</td><td>{_fmt(fl.get('impacted_area_km2'), 2)}</td>"
                 f"<td>{_fmt(fl.get('max_depth_m'), 1)}</td><td>{_fmt(ex.get('buildings_ds_ge3'), 0)}</td><td>{_money(ex.get('direct_loss_pkr'))}</td></tr>")
        labels.append(rid[:6]); fa.append(tr.get("failing_area_km2") or 0.0); imp.append(fl.get("impacted_area_km2") or 0.0)
    chart = ""
    if len(labels) >= 2:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 3.2), dpi=110); x = np.arange(len(labels)); ax.bar(x - 0.2, fa, 0.4, label="Failing area (km²)", color="#1FB6AE"); ax.bar(x + 0.2, imp, 0.4, label="Impacted area (km²)", color="#0E4448")
        ax.set_xticks(x); ax.set_xticklabels(labels); ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False); fig.tight_layout(); b = io.BytesIO(); fig.savefig(b, format="png"); plt.close(fig)
        chart = f'<h2>Trend across runs</h2><img src="data:image/png;base64,{base64.b64encode(b.getvalue()).decode()}" alt="Trend">'
    inner = ("<h2>Run summary</h2><table><tr><th>Run</th><th>Scenario</th><th>Failing km&sup2;</th><th>Released m&sup3;</th><th>Impacted km&sup2;</th><th>Max depth m</th><th>Buildings DS&ge;3</th><th>Direct loss</th></tr>"
             f"{rows}</table>{chart}<p class=\"note\">Screening-grade; scenario strengths and friction; losses valued as in SAILAB (JRC maximum damage value, storeys, contents).</p>")
    return _band_page("Batch Run Summary", inner)
