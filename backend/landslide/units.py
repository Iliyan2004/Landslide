"""Unit conversions. Every conversion the methodology flags as an error-prone boundary (§11.2)."""
import numpy as np

G = 9.80665            # m/s^2
RHO_W = 1000.0         # kg/m^3
GAMMA_W = RHO_W * G    # N/m^3


def deg2rad(x): return np.deg2rad(x)
def rad2deg(x): return np.rad2deg(x)
def slope_deg_to_pct(deg): return 100.0 * np.tan(np.deg2rad(deg))      # 35 % != 35 deg
def slope_pct_to_deg(pct): return np.rad2deg(np.arctan(np.asarray(pct) / 100.0))
def km2_to_m2(x): return np.asarray(x) * 1.0e6
def mm_per_h_to_m_per_s(x): return np.asarray(x) * 1.0e-3 / 3600.0
def m_per_s_to_mm_per_h(x): return np.asarray(x) * 3600.0 * 1.0e3
def kpa_to_pa(x): return np.asarray(x) * 1.0e3
def pa_to_kpa(x): return np.asarray(x) * 1.0e-3
def kn_m3_to_n_m3(x): return np.asarray(x) * 1.0e3
def g_to_ms2(a_g): return np.asarray(a_g) * G
def mm_per_h_over_hours_to_depth_mm(rate_mm_h, hours): return np.asarray(rate_mm_h) * hours
def kelvin_to_celsius(k): return np.asarray(k) - 273.15

# SoilGrids 2.0 stored-integer -> conventional units (docs.isric.org/globaldata/soilgrids).
SOILGRIDS_SCALE = {
    "sand": 0.1, "silt": 0.1, "clay": 0.1,    # g/kg -> %
    "bdod": 0.01,                              # cg/cm3 -> kg/dm3 (== g/cm3)
    "cfvo": 0.1,                               # cm3/dm3 -> % vol
    "soc": 0.1,                                # dg/kg -> g/kg
}
def soilgrids_to_conventional(var, raw):
    if var not in SOILGRIDS_SCALE:
        raise KeyError(f"No documented SoilGrids scale factor for '{var}'")
    return np.asarray(raw, dtype="float64") * SOILGRIDS_SCALE[var]
