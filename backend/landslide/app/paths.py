"""One place for every server dataset path (same idea as SAILAB's data_paths.py).
Override the share root with LANDSLIDE_SHARE, or any single path with LANDSLIDE_<NAME>."""
import os

_cands = [os.environ.get("LANDSLIDE_SHARE"), os.path.expanduser("~/Desktop/DGX-Shared"), os.path.expanduser("~/DGX-Shared")]
SHARE = next((c for c in _cands if c and os.path.isdir(c)), _cands[1])
_LSM = os.path.join(SHARE, "MERGED LANDSLIDE LAYERS", "LSM_CNN_DNN", "outputs")

# name: (path, required)
_DEFAULTS = {
    "DEM": (os.path.join(SHARE, "3. Raster Data", "DEM_SRTM", "pakDEM", "Pak_srtm.tif"), True),
    "LSM_PROB": (os.path.join(_LSM, "04_maps", "susceptibility_prob_Ensemble.tif"), True),
    "LSM_CLASS": (os.path.join(_LSM, "04_maps", "susceptibility_class_Ensemble.tif"), False),
    "RISK_INDEX": (os.path.join(_LSM, "05_risk", "risk_index.tif"), False),
    "HAZARD_EFFECTIVE": (os.path.join(_LSM, "05_risk", "hazard_effective.tif"), False),
    "EXPOSURE_INDEX": (os.path.join(_LSM, "05_risk", "exposure_index.tif"), False),
    "POPULATION": (os.path.join(_LSM, "05_risk", "exposure", "population.tif"), False),
    "BUILT_FRAC": (os.path.join(_LSM, "05_risk", "exposure", "built_frac.tif"), False),
    "ROADS_M": (os.path.join(_LSM, "05_risk", "exposure", "roads_m.tif"), False),
    "HEALTH": (os.path.join(_LSM, "05_risk", "exposure", "health.tif"), False),
    "SCHOOLS": (os.path.join(_LSM, "05_risk", "exposure", "schools.tif"), False),
    "LULC": (os.path.join(_LSM, "01_layers", "lulc.tif"), False),
    "FAULT_DIST": (os.path.join(_LSM, "01_layers", "dist_faults.tif"), False),
    "FAULTS_SHP": (os.path.join(SHARE, "4. Vector Data", "Fault lines", "Fault_lines.shp"), False),
    "BOUNDARY_SHP": (os.path.join(SHARE, "4. Vector Data", "Pakistan Boundary", "Pakistan, Tehsil and District Boundaries", "Pakistan_Boundary.shp"), True),
    "DISTRICTS_SHP": (os.path.join(SHARE, "4. Vector Data", "Pakistan Boundary", "Pakistan, Tehsil and District Boundaries", "District_Boundary.shp"), False),
}
PATHS = {k: os.environ.get(f"LANDSLIDE_{k}", v[0]) for k, v in _DEFAULTS.items()}


def get(name):
    return PATHS[name]


def check():
    return [{"name": k, "path": PATHS[k], "exists": os.path.exists(PATHS[k]), "required": _DEFAULTS[k][1]} for k in _DEFAULTS]
