import json, tempfile, time, unittest
import numpy as np
from landslide.api import service as S
from landslide.api.jobs import JobStore
from landslide.errors import GateError, InsufficientData

SQ = {"type": "Polygon", "coordinates": [[[74.0, 35.0], [74.2, 35.0], [74.2, 35.2], [74.0, 35.2], [74.0, 35.0]]]}
PARAMS = {"soil_depth": {"min": 1, "max": 3}, "effective_cohesion": {"min": 2e3, "max": 8e3}, "friction_angle": {"min": 28, "max": 38},
          "hydraulic_conductivity": {"min": 1e-6, "max": 1e-4}, "water_table": {"min": 2, "max": 6}}


class TestService(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp(); self.aoi = S.validate_aoi(SQ)

    def req(self, **kw):
        return {"aoi_sha256": self.aoi["aoi_sha256"], "slope_deg": 32.0, "rain_mm_step": [0] * 6 + [8.0] * 24, "params": PARAMS, "n": 50, **kw}

    def test_stability_manifest_idempotent_and_flags(self):
        a = S.run_stability(self.req(), run_root=self.d); b = S.run_stability(self.req(), run_root=self.d)
        self.assertEqual(a["run_id"], b["run_id"])
        m = a["manifest"]; self.assertTrue(m["not_for_engineering_design"]); self.assertEqual(m["validation_status"], "screening_only")
        self.assertIn("soil strength not measured", m["warnings"])

    def test_result_is_json_serialisable(self):
        r = S.run_stability(self.req(), run_root=self.d)
        json.dumps(r)   # must not raise (numpy leaked into API payload otherwise)

    def test_stability_missing_params_gate(self):
        bad = dict(PARAMS); bad["water_table"] = None
        with self.assertRaises(GateError): S.run_stability(self.req(params=bad), run_root=self.d)

    def test_grid_stability(self):
        slope = np.array([[10.0, 30.0], [40.0, np.nan]])
        r = S.run_stability(self.req(slope_deg=slope.tolist(), n=5), run_root=self.d)
        self.assertIn("min_fs_p50_stats", r["summary"])

    def test_seismic_needs_ground_motion(self):
        with self.assertRaises(InsufficientData): S.run_seismic({"aoi_sha256": "x", "slope_deg": 30, "params": {}}, run_root=self.d)
        r = S.run_seismic({"aoi_sha256": "x", "slope_deg": 30, "pga_g": 0.4, "params": {"soil_depth": 2, "effective_cohesion": 4e3, "friction_angle": 33}}, run_root=self.d)
        self.assertIn("liquefaction_not_covered", r["summary"]["flags"])

    def test_runout_requires_source(self):
        y, x = np.mgrid[0:20, 0:40]; dem = (300 - 3 * x).astype(float); src = np.zeros(dem.shape, bool)
        with self.assertRaises(GateError):
            S.run_runout({"aoi_sha256": "x", "dem": dem, "source_mask": src, "dx": 30, "volume_m3": 1e4, "alpha_range_deg": [10, 20]}, run_root=self.d)
        src[10, 1] = True
        r = S.run_runout({"aoi_sha256": "x", "dem": dem, "source_mask": src, "dx": 30, "volume_m3": 1e4, "alpha_range_deg": [10, 20], "n": 4}, run_root=self.d)
        self.assertTrue(r["summary"]["status"]["not_simulated_extent"])

    def test_sediment_requires_width_for_volume(self):
        r = S.run_sediment({"aoi_sha256": "x", "hydraulics": {"n": 0.04, "V": [3.0], "h": [1.5], "d50": 0.02}}, run_root=self.d)
        self.assertIsNone(r["summary"]["bedload_total_m3s"])
        with self.assertRaises(InsufficientData): S.run_sediment({"aoi_sha256": "x"}, run_root=self.d)

    def test_jobs_states_and_idempotency(self):
        js = JobStore(1)
        j1 = js.submit("t", "k", lambda progress: {"ok": 1}); j2 = js.submit("t", "k", lambda progress: {"ok": 2})
        self.assertEqual(j1, j2); time.sleep(0.2); self.assertEqual(js.get(j1)["state"], "succeeded")
        j3 = js.submit("t", "k3", lambda progress: S.run_seismic({"aoi_sha256": "x", "slope_deg": 30, "params": {}}, run_root=self.d))
        time.sleep(0.2); self.assertEqual(js.get(j3)["state"], "insufficient_data")

    def test_watch_never_confirms(self):
        w = S.run_watch({"threshold": {"alpha": 10, "beta": 0.5}, "duration_h": 6, "intensity_mm_h": 20})
        self.assertIn(w["tier"], ("none", "watch", "elevated_watch")); self.assertIn("not a confirmed landslide", w["disclaimer"])


if __name__ == "__main__":
    unittest.main()
