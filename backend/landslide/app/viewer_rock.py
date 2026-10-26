"""Builds the standalone 3D rockfall scene (rocks, trails, dust over Mapbox terrain; reach / energy / bounce maps; buildings and roads by energy class).
Uses SAILAB's viewer stylesheet for the panel and timeline so the two products look alike; the scene itself is rockfall-specific."""
from __future__ import annotations
import base64, json, os
import numpy as np

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "viewer")
CLS_COL = ["#f2d94e", "#f0883e", "#d93a2a", "#8a1230", "#5a1a8a"]


def _asset(n):
    with open(os.path.join(HERE, n), encoding="utf-8") as f:
        return f.read()


def _b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


BODY = """<div id="map"></div>
<button id="fsBtn" title="Full screen">&#9974;</button>
<div id="panel" class="glass">
  <div class="ph"><div class="t"><h1>__TITLE__</h1><div class="sub" id="panelSub"></div></div>
    <button class="iconbtn" id="resetBtn" title="Reset view">&#8634;</button><button class="iconbtn" id="collapseBtn" title="Collapse panel">&#8963;</button></div>
  <div class="body">
    <div id="modeSection"><div class="sec" style="margin-top:0">What to show</div>
      <div class="cards">
        <button class="card c-rocks active" data-mode="rocks"><span>Rocks in motion</span></button>
        <button class="card c-reach" data-mode="reach"><span>Reach probability</span></button>
        <button class="card c-energy" data-mode="energy"><span>Peak energy</span></button>
        <button class="card c-bounce" data-mode="bounce"><span>Bounce height</span></button>
      </div>
      <div class="legendbar" id="legendBar"></div><div class="legendlbl" id="legendLbl"></div><div class="legendnote" id="legendNote"></div></div>
    <div class="sec">Map style</div>
    <div class="tiles"><button class="tile t-dark" data-style="dark"><span>Dark</span></button><button class="tile t-light" data-style="light"><span>Light</span></button>
      <button class="tile t-satellite active" data-style="satellite"><span>Satellite</span></button><button class="tile t-streets" data-style="streets"><span>Streets</span></button>
      <button class="tile t-terrain" data-style="terrain"><span>Terrain</span></button><button class="tile t-night" data-style="night"><span>Night</span></button></div>
    <div class="sec">On the map</div>
    <div class="pills"><button class="pill on" id="pillBuildings">Buildings</button><button class="pill on" id="pillTerrain">Terrain</button><button class="pill" id="pillLabels">Labels</button>
      <button class="pill on" id="pillTrails">Trails</button><button class="pill on" id="pillDust">Dust</button></div>
    <details class="fine"><summary><span>Fine-tune</span></summary><div class="in">
      <div class="row">Terrain<input type="range" id="exagSlider" min="0.5" max="3" step="0.1" value="1.4"><output id="exagSliderOut">1.4</output></div>
      <div class="row">Opacity<input type="range" id="opSlider" min="20" max="100" step="5" value="80"><output id="opSliderOut">80</output></div>
      <div class="row">Rock size<input type="range" id="sizeSlider" min="1" max="12" step="0.5" value="1"><output id="sizeSliderOut">1</output></div>
      <div class="row">Trail<input type="range" id="trailSlider" min="6" max="58" step="2" value="36"><output id="trailSliderOut">36</output></div></div></details>
    <details class="fine"><summary><span>Legend &amp; method</span></summary><div class="about">__LEGEND__</div></details>
    <div class="hint">Right-drag (or Ctrl+drag) to rotate &amp; tilt &middot; scroll to zoom &middot; <b style="color:var(--ink)">click the map</b> for reach, energy and bounce height</div>
  </div></div>
<div class="glass" id="timelineBar" style="display:none">
  <div class="tl-top"><button id="playPauseBtn" title="Play/pause">&#10074;&#10074;</button>
    <div><div class="big" id="timeBig">0:00</div><div class="mut" id="timeSub">since release</div></div>
    <div class="stat"><div class="mut" style="margin:0 0 3px">Rocks moving</div><div class="v" id="stMoving">-</div></div>
    <div class="stat"><div class="mut" style="margin:0 0 3px">Stopped</div><div class="v" id="stStopped">-</div></div>
    <div class="stat"><div class="mut" style="margin:0 0 3px">Fastest</div><div class="v" id="stSpeed">-</div></div>
    <div class="stat"><div class="mut" style="margin:0 0 3px">Peak energy</div><div class="v" id="stEnergy">-</div></div>
    <div class="sp"></div><button class="tbtn" id="exportPngBtn">&#9635; PNG</button><button class="tbtn" id="exportVideoBtn">&#9635; Video (MP4)</button></div>
  <div id="chartWrap"><canvas id="chart" style="width:100%;height:60px"></canvas></div>
  <div class="tl-bot"><span id="timeLabel" style="font-variant-numeric:tabular-nums;min-width:80px"></span><input type="range" id="timeSlider" min="0" max="1000" value="0" step="1">
    <span>Playback</span><select id="speedSelect"><option value="0.5">0.5&times;</option><option value="1" selected>1&times;</option><option value="2">2&times;</option><option value="4">4&times;</option></select></div>
</div>"""
EXTRA_CSS = (".c-rocks{background:radial-gradient(circle at 30% 60%,#7b6a58,transparent 50%),radial-gradient(circle at 65% 45%,#f0883e,transparent 35%),linear-gradient(135deg,#252018,#12100c)}"
             ".c-reach{background:radial-gradient(circle at 50% 55%,#e8602a,transparent 62%),linear-gradient(135deg,#2c2418,#17120c)}"
             ".c-energy{background:linear-gradient(110deg,#251a38 0%,#8a1230 45%,#f0883e 75%,#faf0a0 100%)}"
             ".c-bounce{background:radial-gradient(circle at 40% 70%,#3d8ad6,transparent 55%),linear-gradient(135deg,#172433,#0d1620)}")


def build(out_path, title, aoi, token, epsg, affine, arrays, rocks, sources_lonlat, buildings, roads, barriers, stats, res, legend=""):
    from pyproj import Transformer
    reach = np.nan_to_num(arrays["reach_frac"]); emax = np.nan_to_num(arrays["emax_kj"]); hmax = np.nan_to_num(arrays["hmax_m"])
    act = (reach > 0)
    sl = np.asarray(sources_lonlat)
    tr_ll = Transformer.from_crs(4326, epsg, always_xy=True)
    if len(sl):
        sx, sy = tr_ll.transform(sl[:, 0], sl[:, 1]); sc, sr = (~affine) * (np.asarray(sx), np.asarray(sy)); act[np.clip(sr.astype(int), 0, act.shape[0] - 1), np.clip(sc.astype(int), 0, act.shape[1] - 1)] = True
    rows, cols = np.where(act)
    m = 10
    r0, r1 = max(0, rows.min() - m), min(act.shape[0], rows.max() + m + 1); c0, c1 = max(0, cols.min() - m), min(act.shape[1], cols.max() + m + 1)
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    corners = [tr.transform(*(affine * (c0, r0))), tr.transform(*(affine * (c1, r0))), tr.transform(*(affine * (c1, r1))), tr.transform(*(affine * (c0, r1)))]
    bbox = [min(p[0] for p in corners), min(p[1] for p in corners), max(p[0] for p in corners), max(p[1] for p in corners)]
    rc, ec, hc = reach[r0:r1, c0:c1], emax[r0:r1, c0:c1], hmax[r0:r1, c0:c1]
    nr, nc = rc.shape
    rmax = float(max(rc.max(), 1e-3)); emx = float(max(ec.max(), 1.0)); hmx = float(max(hc.max(), 0.5))
    q = lambda a: np.clip(np.rint(a * 255), 0, 255).astype("uint8")
    reach_q = np.where(rc > 0, np.maximum(q(np.sqrt(rc / rmax)), 1), 0).astype("uint8")
    en_q = np.where(ec > 0.01, np.maximum(q(np.log10(1 + ec) / np.log10(1 + emx)), 1), 0).astype("uint8")
    bo_q = np.where(hc > 0.05, np.maximum(q(hc / hmx), 1), 0).astype("uint8")
    # reach is sqrt-encoded: decode in JS as (q/255)^2 * max -> store the decoded max and let the JS square it
    lon = rocks["lon"].astype("float64") - bbox[0]; lat = rocks["lat"].astype("float64") - bbox[1]
    nrec, M = lon.shape
    rk = {"nrec": int(nrec), "m": int(M), "dt": float(rocks["dt"]), "lonB64": _b64(lon.astype("float32")), "latB64": _b64(lat.astype("float32")), "hB64": _b64(rocks["h"].astype("float32")),
          "vB64": _b64(rocks["v"].astype("float32")), "impB64": _b64(rocks["imp"].astype("uint8")), "stateB64": _b64(rocks["state"].astype("uint8")), "diaB64": _b64(rocks["dia"].astype("float32"))}

    def bcls_color(c):
        return CLS_COL[c] if c is not None and c >= 0 else "#d9d4c8"
    bf = []
    for b in sorted([x for x in buildings if "reach" in x], key=lambda x: -(x.get("emax_kj") or 0) * (1 if x.get("cls", -1) >= 0 else 0))[:8000]:
        bf.append({"type": "Feature", "properties": {"height_m": b["height_m"], "color": bcls_color(b.get("cls"))}, "geometry": {"type": "Polygon", "coordinates": [b["coords_lonlat"]]}})
    rf = [{"type": "Feature", "properties": {"color": bcls_color(r_.get("cls")) if r_.get("cls", -1) >= 0 else "rgba(0,0,0,0)"}, "geometry": {"type": "LineString", "coordinates": r_["coords_lonlat"]}} for r_ in roads]
    bar = [{"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": b["coords"]}} for b in (barriers or [])]
    src = [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [float(a), float(b)]}} for a, b in sl[:400]]
    # camera: look up the slope from below (from where the rocks stop toward where they start)
    cam = {"pitch": 58.0, "bearing": 0.0}
    st = rocks["state"][-1] if len(rocks["state"]) else None
    la, lo = rocks["lat"], rocks["lon"]
    if nrec > 2 and len(sl):
        e = float(np.mean(sl[:, 0]) - np.mean(lo[-1])) * np.cos(np.radians(np.mean(la[-1]))); n_ = float(np.mean(sl[:, 1]) - np.mean(la[-1]))
        if np.hypot(e, n_) > 1e-5:
            cam["bearing"] = float(np.degrees(np.arctan2(e, n_)))
    payload = {"bbox": bbox, "center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], "ncols": int(nc), "nrows": int(nr), "cell_m": float(res), "aoi": aoi if aoi["type"] == "Polygon" else None, "token": token,
               "maps": {"reachB64": _b64(reach_q), "reachMax": 1.0, "energyB64": _b64(en_q), "energyMax": emx, "bounceB64": _b64(bo_q), "bounceMax": hmx},
               "rocks": rk, "buildings": {"type": "FeatureCollection", "features": bf}, "roads": {"type": "FeatureCollection", "features": rf},
               "barriers": {"type": "FeatureCollection", "features": bar}, "sources": {"type": "FeatureCollection", "features": src}, "cam": cam,
               "stats": {"rocks": stats["rocks"], "sources": stats["sources"], "peakEnergyKj": float(emx)}}
    # the reach map is stored as sqrt(reach/rmax); the viewer squares it and multiplies by reachMax
    payload["maps"]["reachMax"] = rmax
    js = _asset("rock_scene.js").replace("__PAYLOAD__", json.dumps(payload).replace("</", "<\\/"))
    # decode of the reach map: sqrt-encoded
    js = js.replace("const re = q('reach') * MAPS.reach.max", "const re = q('reach') * q('reach') * MAPS.reach.max")
    body = BODY.replace("__TITLE__", title).replace("__LEGEND__", legend or "")
    html = ("<!doctype html>\n<title>" + title + "</title>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<link href=\"https://api.mapbox.com/mapbox-gl-js/v3.6.0/mapbox-gl.css\" rel=\"stylesheet\">\n<style>\n" + _asset("mapbox3d_style.css") + "\n" + EXTRA_CSS + "\n</style>\n" + body +
            "\n<script src=\"https://unpkg.com/three@0.160.0/build/three.min.js\"></script>\n<script src=\"https://api.mapbox.com/mapbox-gl-js/v3.6.0/mapbox-gl.js\"></script>\n<script>\n" + js + "\n</script>\n")
    open(out_path, "w").write(html)
    return {"bbox": bbox, "size_bytes": os.path.getsize(out_path), "tracked_rocks": int(M), "records": int(nrec)}
