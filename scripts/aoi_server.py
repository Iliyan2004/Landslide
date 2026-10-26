"""Dashboard server with area-of-interest fetching.

  GET  /                     the Gilgit sample dashboard (site/index.html)
  GET  /a/<id>/              a dashboard built for a user-drawn area (datasets/aoi/<id>/index.html)
  GET  /api/health           {"ok": true}
  GET  /api/aois             the areas built so far
  POST /api/aoi              {"geometry": GeoJSON Polygon (lon/lat), "name": str, "deep": bool}  ->  {"state": "done"|"started", "id", "job"}
  GET  /api/job/<job>        {"state": "running"|"done"|"failed", "messages": [...], "elapsed": s, "id", "error"}
Areas are built by aoi_builder.py (national DEM, Earth Engine and local files) one at a time; a repeat request for the same polygon returns
the stored page. Usage: python -X utf8 scripts/aoi_server.py [--port 8080]
"""
import argparse, json, mimetypes, sys, threading, time, traceback, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import aoi_builder as B

LP = Path(__file__).resolve().parents[1]
SITE = LP / "site"
AOI_DIR = LP / "datasets/aoi"
JOBS = {}
LOCK = threading.Lock()
HIST = {}
HIST_LOCK = threading.Semaphore(2)
BUILD = threading.Semaphore(1)          # one area at a time: each one makes many Earth Engine requests


def run_job(job, geom, name, deep):
    job["state"] = "queued"
    with BUILD:
        job["state"] = "running"; job["t0"] = time.time()
        try:
            def prog(m): job["messages"].append(m)
            B.build_aoi(geom, name, AOI_DIR / job["id"], progress=prog, deep=deep, aoi_key=job["id"])
            job["state"] = "done"
        except B.AOIError as e:
            job["state"] = "failed"; job["error"] = str(e)
        except Exception as e:
            traceback.print_exc()
            job["state"] = "failed"; job["error"] = f"{type(e).__name__}: {e}"
        job["t1"] = time.time()


def list_aois():
    out = []
    for m in sorted(AOI_DIR.glob("*/meta.json"), key=lambda p: -p.stat().st_mtime):
        try:
            j = json.loads(m.read_text(encoding="utf-8"))
            out.append(dict(id=j["id"], name=j["name"], area_km2=j["area_km2"], events=j["events"], deep=j["deep"], built=j["built"]))
        except Exception:
            pass
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

    def send_file(self, p: Path):
        if not p.exists() or not p.is_file():
            self.send_response(404); self.end_headers(); return
        data = p.read_bytes()
        self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(str(p))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"): return self.send_file(SITE / "index.html")
        if path == "/config.js": return self.send_file(SITE / "config.js")
        if path == "/api/health": return self.send_json({"ok": True})
        if path == "/api/aois": return self.send_json({"aois": list_aois()})
        if path.startswith("/api/job/"):
            j = JOBS.get(path.rsplit("/", 1)[1])
            if not j: return self.send_json({"error": "unknown job"}, 404)
            el = int((j.get("t1") or time.time()) - j["t0"]) if j.get("t0") else 0
            return self.send_json({"state": "running" if j["state"] in ("queued", "running") else j["state"], "messages": j["messages"], "elapsed": el, "id": j["id"], "error": j.get("error")})
        if path == "/api/hist":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            try:
                lon, lat, date = float(q["lon"][0]), float(q["lat"][0]), q["date"][0][:10]
                key = (round(lon, 4), round(lat, 4), date)
                if key not in HIST:
                    import aoi_hist
                    with HIST_LOCK:
                        HIST[key] = aoi_hist.hist_assess(lon, lat, date)
                return self.send_json(HIST[key])
            except Exception as e:
                return self.send_json({"error": f"{type(e).__name__}: {e}"}, 400)
        if path.startswith("/a/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2 and parts[1].isalnum(): return self.send_file(AOI_DIR / parts[1] / "index.html")
        self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path != "/api/aoi":
            self.send_response(404); self.end_headers(); return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            geom = body["geometry"]
            if geom.get("type") != "Polygon" or len(geom["coordinates"][0]) < 4: raise ValueError("a polygon with at least three corners is needed")
            for lo, la in geom["coordinates"][0]:
                if not (55 <= lo <= 82 and 20 <= la <= 40): raise ValueError("the polygon must lie in Pakistan")
            name = str(body.get("name") or "My area")[:80]; deep = bool(body.get("deep", True))
            B.make_grid(geom)                                       # validates size and coverage before any work starts
        except B.AOIError as e:
            return self.send_json({"error": str(e)}, 400)
        except Exception as e:
            return self.send_json({"error": str(e)}, 400)
        aid = B.aoi_id(geom, deep)
        if (AOI_DIR / aid / "index.html").exists():
            return self.send_json({"state": "done", "id": aid})
        with LOCK:
            for jid, j in JOBS.items():
                if j["id"] == aid and j["state"] in ("queued", "running"):
                    return self.send_json({"state": "started", "id": aid, "job": jid})
            jid = uuid.uuid4().hex[:10]
            job = dict(id=aid, state="queued", messages=["queued"], t0=time.time())
            JOBS[jid] = job
        threading.Thread(target=run_job, args=(job, geom, name, deep), daemon=True).start()
        self.send_json({"state": "started", "id": aid, "job": jid})


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8080); a = ap.parse_args()
    AOI_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print(f"serving on http://localhost:{a.port}/  (areas are stored in {AOI_DIR})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
