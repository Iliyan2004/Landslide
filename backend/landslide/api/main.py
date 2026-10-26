"""FastAPI app (§7.2). Run: uvicorn landslide.api.main:app --reload   (requires fastapi, uvicorn, pydantic).
Auth: set LANDSLIDE_API_TOKENS="tok1,tok2"; keys for external data providers stay server-side (ENV)."""
from __future__ import annotations
import io, json, os, zipfile
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from . import service as S
from .jobs import JobStore
from ..errors import GateError
from ..manifest import cache_key

app = FastAPI(title="Landslide Modelling Platform", version="1.0.0")
jobs = JobStore(workers=int(os.environ.get("WORKERS", 2)))
RUNS = Path(os.environ.get("RUNS_DIR", "runs"))
CATALOG = Path(os.environ.get("DATASETS_DIR", "datasets")) / "indices" / "catalog.json"
AOIS: dict = {}


def auth(authorization: str | None = Header(default=None)):
    toks = [t for t in os.environ.get("LANDSLIDE_API_TOKENS", "").split(",") if t]
    if toks and (authorization or "").removeprefix("Bearer ") not in toks:
        raise HTTPException(401, "invalid or missing bearer token")


class AOIIn(BaseModel):
    geometry: dict


class FetchIn(BaseModel):
    aoi_id: str
    source_ids: list[str]


class ModelIn(BaseModel):
    aoi_id: str
    payload: dict = Field(default_factory=dict)


@app.get("/api/health")
def health(): return {"status": "ok", "version": "1.0.0"}


@app.post("/api/aois", dependencies=[Depends(auth)])
def post_aoi(a: AOIIn):
    try:
        r = S.validate_aoi(a.geometry)
    except GateError as e:
        raise HTTPException(422, {"code": e.code, "reasons": e.reasons})
    AOIS[r["aoi_id"]] = {**r, "geometry": a.geometry}
    return r


def _aoi(aoi_id):
    if aoi_id not in AOIS:
        raise HTTPException(404, "unknown aoi_id (never substituting another AOI)")
    return AOIS[aoi_id]


@app.get("/api/data/status", dependencies=[Depends(auth)])
def data_status(aoid: str):
    _aoi(aoid)
    cat = json.loads(CATALOG.read_text()) if CATALOG.exists() else {}
    reg = ["D01", "D04", "D06", "D07", "D11", "D14", "D15", "D16", "D23", "D40"]   # Tier S minimum (§2.2)
    return {"aoi_id": aoid, "coverage": {r: cat.get(aoid, {}).get(r, "missing") for r in reg}}


@app.post("/api/data/fetch", dependencies=[Depends(auth)])
def data_fetch(f: FetchIn):
    from ..data.fetchers.sources import REGISTRY
    a = _aoi(f.aoi_id)
    unknown = [s for s in f.source_ids if s not in REGISTRY]
    if unknown:
        raise HTTPException(422, {"unknown_sources": unknown, "available": sorted(REGISTRY)})
    def work(progress):
        out = []
        for i, sid in enumerate(f.source_ids):
            progress(f"fetch {sid}", i / len(f.source_ids))
            r = REGISTRY[sid]().fetch(a["bbox"], Path("datasets/raw") / sid)
            out.append(r.__dict__)
        return out
    return {"job_id": jobs.submit("fetch", cache_key("fetch", "1", [{"id": s} for s in f.source_ids], a["aoi_sha256"], {}, {}), work)}


@app.get("/api/layers", dependencies=[Depends(auth)])
def layers(aoid: str):
    _aoi(aoid)
    return {"aoi_id": aoid, "layers": [{"id": n, "kind": k} for n, k in [
        ("dem", "raster"), ("hillshade", "raster"), ("slope", "raster"), ("lithology", "vector"), ("landcover", "raster"),
        ("rainfall", "timeseries"), ("pga", "raster"), ("inventory", "vector"), ("roads_assets", "vector")]]}


def _model_endpoint(kind, fn):
    def handler(m: ModelIn):
        a = _aoi(m.aoi_id)
        req = {**m.payload, "aoi_sha256": a["aoi_sha256"]}
        key = cache_key(kind, S.MODEL_VERSION, [], a["aoi_sha256"], {}, m.payload)
        return {"job_id": jobs.submit(kind, key, lambda progress: fn(req, progress=progress, run_root=RUNS))}
    app.post(f"/api/models/{kind}", dependencies=[Depends(auth)])(handler)


for _k, _f in (("stability", S.run_stability), ("seismic", S.run_seismic), ("runout", S.run_runout), ("sediment", S.run_sediment)):
    _model_endpoint(_k, _f)


@app.post("/api/models/susceptibility", dependencies=[Depends(auth)])
def susceptibility(m: ModelIn):
    raise HTTPException(501, "Wire prepared feature stack + inventory (landslide.models.susceptibility); see docs/RUNBOOK.md")


@app.post("/api/scenarios/compare", dependencies=[Depends(auth)])
def compare(body: dict):
    ids = body.get("run_ids", [])
    out = {}
    for r in ids:
        p = RUNS / r / "summary.json"
        if not p.exists():
            raise HTTPException(404, f"run {r} not found")
        out[r] = json.loads(p.read_text())
    return {"runs": out, "note": "compare only runs on identical grid and inventory snapshot"}


@app.post("/api/monitor/watch", dependencies=[Depends(auth)])
def watch(body: dict): return S.run_watch(body)


@app.get("/api/jobs/{jid}", dependencies=[Depends(auth)])
def job(jid: str):
    j = jobs.get(jid)
    if not j: raise HTTPException(404, "unknown job")
    return {k: v for k, v in j.items() if k != "cancel"}


@app.delete("/api/jobs/{jid}", dependencies=[Depends(auth)])
def cancel(jid: str):
    if not jobs.cancel(jid): raise HTTPException(404, "unknown job")
    return {"cancelled": True}


@app.get("/api/results/{rid}/manifest", dependencies=[Depends(auth)])
def manifest(rid: str):
    p = RUNS / rid / "manifest.json"
    if not p.exists(): raise HTTPException(404, "no manifest")
    return JSONResponse(json.loads(p.read_text()))


@app.get("/api/results/{rid}/tiles/{z}/{x}/{y}", dependencies=[Depends(auth)])
def tiles(rid: str, z: int, x: int, y: int):
    p = RUNS / rid / "tiles" / str(z) / str(x) / f"{y}.png"
    if not p.exists(): raise HTTPException(404, "tile not rendered (tile rendering is a separate worker job; see docs/RUNBOOK.md)")
    return FileResponse(p, media_type="image/png")


@app.get("/api/results/{rid}/download", dependencies=[Depends(auth)])
def download(rid: str):
    d = RUNS / rid
    if not (d / "manifest.json").exists(): raise HTTPException(404, "unknown run")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file(): z.write(f, f.relative_to(d))
        z.writestr("README.txt", "Run bundle: manifest.json lists inputs, hashes, parameters, warnings.\n" + S.DISCLAIMER + "\n")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={rid}.zip"})
