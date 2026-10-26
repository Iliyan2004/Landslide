"""§11.2 data-integrity tests: units, terrain, gates, manifest/caching, ML leakage guards."""
import unittest, tempfile, json
import numpy as np
from landslide import units as U, gates as G, manifest as M
from landslide.data.preprocessing import terrain as T
from landslide.errors import GateError
from landslide.models.susceptibility import statistical as S, legacy as L
from landslide.models.monitoring import thresholds as TH
from landslide.models.exposure import exposure as X


class TestUnits(unittest.TestCase):
    def test_slope_pct_vs_deg(self):
        self.assertAlmostEqual(float(U.slope_deg_to_pct(35)), 70.02, places=1)
        self.assertAlmostEqual(float(U.slope_pct_to_deg(35)), 19.29, places=1)

    def test_conversions(self):
        self.assertAlmostEqual(float(U.mm_per_h_to_m_per_s(3.6)), 1e-6)
        self.assertEqual(float(U.km2_to_m2(2)), 2e6); self.assertEqual(float(U.kpa_to_pa(5)), 5000)
        self.assertAlmostEqual(float(U.soilgrids_to_conventional("sand", 450)), 45.0)
        with self.assertRaises(KeyError): U.soilgrids_to_conventional("ph", 1)


class TestTerrain(unittest.TestCase):
    def test_plane_slope_aspect(self):
        x = np.tile(np.arange(40), (40, 1)) * 1.0
        dem = np.tan(np.deg2rad(30)) * 30 * x
        r = T.slope_aspect(dem, 30, 30)
        self.assertAlmostEqual(r["slope_deg"][20, 20], 30.0, places=6)
        self.assertAlmostEqual(r["aspect_deg"][20, 20], 270.0, places=6)    # downslope to west

    def test_flat_has_nan_aspect(self):
        self.assertTrue(np.isnan(T.slope_aspect(np.ones((5, 5)), 30, 30)["aspect_deg"]).all())

    def test_flow_acyclic_and_conserves_cells(self):
        rng = np.random.default_rng(2)
        y, x = np.mgrid[0:50, 0:50]
        dem = 500 - 2 * x - 1 * y + rng.normal(0, 0.5, (50, 50))
        f = T.fill_pits(dem)
        self.assertTrue(np.all(f >= dem - 1e-12))
        fl = T.d8_flow(f, 30, 30)
        G.check_flow_graph_acyclic(fl["downstream"])
        self.assertGreaterEqual(fl["flow_accum_cells"].max(), 1)
        outlets = fl["downstream"] == -1
        self.assertEqual(round(fl["flow_accum_cells"][outlets].sum()), 2500)   # every cell drains to an outlet

    def test_cycle_detected(self):
        with self.assertRaises(GateError): G.check_flow_graph_acyclic(np.array([1, 0]))

    def test_twi_floors_zero_slope(self):
        h = T.hydrology_indices(np.zeros((3, 3)), np.ones((3, 3)), 30, 30)
        self.assertTrue(np.isfinite(h["TWI"]).all())


class TestGates(unittest.TestCase):
    def test_crs_mismatch_reported(self):
        g = {"a": dict(crs="EPSG:32643", transform=(0, 30, 0, 0, 0, -30), shape=(10, 10)),
             "b": dict(crs="EPSG:32642", transform=(0, 30, 0, 0, 0, -30), shape=(10, 10))}
        with self.assertRaises(GateError) as cm: G.check_grid_compat(g)
        self.assertIn("CRS", str(cm.exception))

    def test_nodata_fraction(self):
        a = np.ones((10, 10)); a[:3] = np.nan
        with self.assertRaises(GateError): G.check_nodata_fraction(a, np.ones_like(a, bool), 0.10)

    def test_timestamps_and_provenance(self):
        with self.assertRaises(GateError): G.check_timestamps_utc(np.array(["2025-07-01T00", "2025-07-01T00"], "datetime64[h]"))
        with self.assertRaises(GateError): G.check_provenance({"source_id": "imerg"})

    def test_supervised_needs_inventory(self):
        with self.assertRaises(GateError): G.check_supervised_inventory(3)


class TestManifest(unittest.TestCase):
    def test_cache_key_deterministic_and_sensitive(self):
        a = M.cache_key("m", "1", [{"id": "d1", "sha256": "x"}], "aoi", {"r": 30}, {"p": 1})
        self.assertEqual(a, M.cache_key("m", "1", [{"id": "d1", "sha256": "x"}], "aoi", {"r": 30}, {"p": 1}))
        self.assertNotEqual(a, M.cache_key("m", "1", [{"id": "d1", "sha256": "y"}], "aoi", {"r": 30}, {"p": 1}))

    def test_manifest_written_and_flags(self):
        m = M.build_manifest("infinite_slope_green_ampt", "1.0.0", [], "h", {"crs": "EPSG:32643", "resolution_m": 30})
        self.assertTrue(m["not_for_engineering_design"])
        with tempfile.TemporaryDirectory() as d:
            p = M.write_manifest(d, m); self.assertEqual(json.loads(p.read_text())["run_id"], m["run_id"])


class TestML(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0); n = 800
        self.xy = rng.uniform(0, 40000, (n, 2)); s = rng.uniform(0, 50, n)
        self.y = (rng.uniform(size=n) < 1 / (1 + np.exp(-0.15 * (s - 30)))).astype(int)
        self.X = np.c_[s, rng.normal(size=n)]

    def test_spatial_blocks_group_whole_cells(self):
        g = S.spatial_blocks(self.xy[:, 0], self.xy[:, 1], 10000)
        self.assertLessEqual(len(np.unique(g)), 16)

    def test_cv_has_skill_and_flags(self):
        g = S.spatial_blocks(self.xy[:, 0], self.xy[:, 1], 10000)
        r = S.spatial_cv(self.X, self.y, g, "logistic")
        self.assertGreater(r["roc_auc"], 0.7); self.assertEqual(r["validation_status"], "spatially_validated")

    def test_ood_suppressed(self):
        m, dom = S.fit_final(self.X, self.y, "logistic")
        p = S.predict(m, np.array([[25.0, 0.0], [500.0, 0.0]]), dom)
        self.assertFalse(p["out_of_domain"][0]); self.assertTrue(np.isnan(p["score_relative"][1]))

    def test_negatives_avoid_positive_buffer(self):
        pos = self.xy[self.y == 1][:20]
        neg = S.sample_negatives(self.xy, np.ones(len(self.xy), bool), pos, 2000, 50)
        from scipy.spatial import cKDTree
        self.assertTrue((cKDTree(pos).query(neg)[0] > 2000).all())

    def test_legacy_nodata_never_low(self):
        cfg = L.load_config(__import__("pathlib").Path(__file__).resolve().parents[2] / "configs" / "legacy_susceptibility.yaml")
        cls, _ = L.score(np.array([10.0, np.nan]), np.array([2.0, 3.0]), cfg)
        self.assertEqual(cls[1], -1)


class TestMonitoringExposure(unittest.TestCase):
    def test_threshold_and_state(self):
        th = TH.fit_id_threshold(np.array([1, 3, 6, 12, 24, 48.]), np.array([30, 15, 9, 5, 3, 1.8]))
        self.assertTrue(th["beta"] > 0)
        self.assertEqual(TH.watch_state(False)["tier"], "none")
        w = TH.watch_state(True, 0.95, True)
        self.assertEqual(w["tier"], "elevated_watch"); self.assertEqual(w["status"], "experimental_unvalidated")
        self.assertTrue(w["stale_data"])

    def test_exposure_and_fragility_guard(self):
        mask = np.zeros((4, 4), bool); mask[1:3, 1:3] = True
        self.assertEqual(X.population_exposed(np.full((4, 4), 10.0), mask), 40.0)
        ins = X.points_in_mask([15, 95], [-15, -95], mask, (0, 30, 0, -30)); self.assertEqual(list(ins), [False, False])
        from landslide.errors import InsufficientData
        with self.assertRaises(InsufficientData): X.damage(1.0, None)


if __name__ == "__main__":
    unittest.main()
