"""Run manifest (§11.1) + deterministic hashing / idempotent cache keys."""
from __future__ import annotations
import hashlib, json, uuid
from datetime import datetime, timezone
from pathlib import Path

CALIBRATION = ("not_calibrated", "calibrated", "calibrated_event_holdout")
VALIDATION = ("screening_only", "spatially_validated", "event_validated", "operationally_validated")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def sha256_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def cache_key(model, model_version, source_data, aoi_sha256, grid, params, forcing_window=None):
    """Cache by source version + AOI geometry + params, NOT display URL (§2.1)."""
    return sha256_obj({"m": model, "v": model_version, "src": sorted(source_data, key=lambda d: d["id"]),
                       "aoi": aoi_sha256, "grid": grid, "p": params, "t": forcing_window})


def build_manifest(model, model_version, source_data, aoi_sha256, grid, time_start_utc=None,
                   time_end_utc=None, parameter_mode="scenario_ensemble",
                   calibration_status="not_calibrated", validation_status="screening_only",
                   warnings=None, results=None, params=None, run_id=None):
    assert calibration_status in CALIBRATION and validation_status in VALIDATION
    return {
        "run_id": run_id or str(uuid.uuid4()),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model, "model_version": model_version,
        "source_data": source_data, "aoi_sha256": aoi_sha256, "grid": grid,
        "time_start_utc": time_start_utc, "time_end_utc": time_end_utc,
        "parameter_mode": parameter_mode,
        "calibration_status": calibration_status, "validation_status": validation_status,
        "not_for_engineering_design": True,
        "warnings": list(warnings or []), "results": list(results or []),
        "params": params or {},
    }


def write_manifest(run_dir, manifest):
    p = Path(run_dir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return p / "manifest.json"
