"""Web API tests with Flask's test client: light endpoints only (no simulations)."""
import os, unittest
import numpy as np
from landslide.app import server as S
from landslide.engine import access as AC, ground as GR

G = {"type": "Polygon", "coordinates": [[[74.28, 35.90], [74.33, 35.90], [74.33, 35.94], [74.28, 35.94], [74.28, 35.90]]]}


class TestApi(unittest.TestCase):
    def setUp(self):
        S.app.testing = True; self.c = S.app.test_client(); S._hits.clear(); os.environ.pop("LANDLAB_TOKEN", None)

    def test_pages_landing_app_instant(self):
        land = self.c.get("/"); self.assertEqual(land.status_code, 200); self.assertIn(b"LANDLAB Instant", land.data); self.assertIn(b'href="/app"', land.data)
        self.assertNotIn(b"SAILAB", land.data.replace(b"base64", b""))
        self.assertEqual(self.c.get("/?import=abc").status_code, 302)                                    # a hand-over goes straight to the app
        app = self.c.get("/app"); self.assertEqual(app.status_code, 200); self.assertIn(b"welcomeOverlay", app.data); self.assertIn(b"geoInput", app.data)
        ins = self.c.get("/instant"); self.assertEqual(ins.status_code, 200); self.assertIn(b"instant-library", ins.data); self.assertNotIn(b"__MAPBOX_TOKEN__", ins.data)

    def test_runfile_load_validation(self):
        good = {"format": "landlab-run-file", "geometry": G, "params": {"mode": "rain", "strength_quantile": 0.4, "bogus": 1, "rain": {"times_h": [1, 2], "rate_mm_h": [5, 6], "source": "x"}}}
        j = self.c.post("/api/runfile/load", json=good).get_json()
        self.assertEqual(j["params"]["strength_quantile"], 0.4); self.assertNotIn("bogus", j["params"]); self.assertEqual(len(j["params"]["rain"]["times_h"]), 2); self.assertTrue(any("bogus" in w for w in j["warnings"]))
        for bad in ({"format": "other"}, {"format": "landlab-run-file", "geometry": {"type": "Point"}}, {"format": "landlab-run-file", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}):
            self.assertEqual(self.c.post("/api/runfile/load", json=bad).status_code, 400)

    def test_custom_dem_rejects_a_non_tiff(self):
        import io
        r = self.c.post("/api/custom-dem", data={"file": (io.BytesIO(b"not a tiff"), "x.tif")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 422); self.assertIn("error", r.get_json())
        self.assertEqual(self.c.post("/api/custom-dem", data={}, content_type="multipart/form-data").status_code, 400)

    def test_page_and_presets(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        j = self.c.get("/api/presets").get_json(); self.assertIn("sandy loam", j["textures"])

    def test_polygon_validation_and_district(self):
        j = self.c.post("/area/polygon", json={"geometry": G}).get_json()
        self.assertAlmostEqual(j["area_km2"], 20.07, delta=0.1); self.assertTrue(j["physics_possible"])
        bad = self.c.post("/area/polygon", json={"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1]]]}})
        self.assertIn(bad.status_code, (400, 422))
        self.assertEqual(self.c.post("/area/polygon", json={}).status_code, 400)

    def test_design_storm_is_validated(self):
        r = self.c.post("/area/design-storm", json={"geometry": G, "T": 37}); self.assertEqual(r.status_code, 400)
        j = self.c.post("/area/design-storm", json={"geometry": G, "T": 50, "duration_h": 6}).get_json()
        self.assertAlmostEqual(j["total_mm"], j["idf_row"]["depth_mm"][3], places=3)

    def test_run_refuses_missing_inputs(self):
        self.assertEqual(self.c.post("/run", json={"geometry": G, "params": {"mode": "rain"}}).status_code, 400)
        self.assertEqual(self.c.post("/run", json={"geometry": G, "params": {"mode": "quake"}}).status_code, 400)
        self.assertEqual(self.c.post("/area/mitigation", json={"geometry": G, "params": {}}).status_code, 400)

    def test_token_and_rate_limit(self):
        os.environ["LANDLAB_TOKEN"] = "s3cret"
        try:
            self.assertEqual(self.c.post("/area/polygon", json={"geometry": G}).status_code, 401)
            ok = self.c.post("/area/polygon", json={"geometry": G}, headers={"Authorization": "Bearer s3cret"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(self.c.get("/api/presets").status_code, 200)            # reads stay open
            os.environ["LANDLAB_RATE"] = "3"; S._hits.clear()
            codes = [self.c.post("/area/polygon", json={"geometry": G}, headers={"X-Token": "s3cret"}).status_code for _ in range(5)]
            self.assertEqual(codes[-1], 429)
        finally:
            os.environ.pop("LANDLAB_TOKEN", None); os.environ.pop("LANDLAB_RATE", None)

    def test_unknown_run_is_404_not_a_crash(self):
        self.assertEqual(self.c.get("/runs/doesnotexist/summary.json").status_code, 404)
        self.assertEqual(self.c.get("/runs/doesnotexist/export.zip").status_code, 404)
        self.assertEqual(self.c.delete("/runs/doesnotexist").status_code, 404)

    def test_cleanup_is_dry_by_default(self):
        j = self.c.post("/runs/cleanup", json={"older_than_days": 99999}).get_json(); self.assertTrue(j["dry_run"])


class TestAccess(unittest.TestCase):
    def test_blocked_junction_isolates_the_branch_and_preexisting_islands_are_not_blamed(self):
        main = [(0, 0), (100, 0), (200, 0), (300, 0), (400, 0)]; br = [(200, 0), (200, 100), (200, 200)]; island = [(1000, 1000), (1100, 1000)]
        r = AC.analyse([main, br, island], [[False] * 4, [True, False], [False]], [(380, 5), (200, 190), (1050, 1005)], ["house"] * 3)
        self.assertEqual(r["cut_off"], 1)                                            # only the branch house; the island was never connected

    def test_no_blocking_means_nobody_is_cut_off(self):
        r = AC.analyse([[(0, 0), (100, 0), (200, 0)]], [[False, False]], [(10, 3), (190, 3)], ["house", "hospital"])
        self.assertEqual(r["cut_off"], 0); self.assertEqual(r["facilities"]["cut_off"], 0)


class TestGround(unittest.TestCase):
    def test_neutral_defaults_leave_strength_unchanged_and_land_cover_sets_roots(self):
        from landslide.app import rasters
        grid = rasters.make_grid((74.30, 35.91, 74.31, 35.92), 32643, 30.0); shp = (grid["height"], grid["width"])
        sp = {"effective_cohesion": 3000.0, "friction_angle": 30.0, "root_cohesion": 1000.0, "soil_depth": 1.5}
        sp2, rep = GR.apply(sp, grid, shp)
        self.assertTrue(np.allclose(sp2["effective_cohesion"], 3000.0)); self.assertTrue(np.allclose(sp2["friction_angle"], 30.0))
        self.assertGreater(rep["landcover_coverage"], 0.9)
        self.assertTrue(np.isin(np.unique(sp2["root_cohesion"]), [0.0, 500.0, 1500.0, 2000.0, 6000.0, 1000.0]).all())


if __name__ == "__main__":
    unittest.main()


class TestCalibrateSusceptibilityInput(unittest.TestCase):
    def test_needs_file_or_susceptibility_source(self):
        from landslide.app.server import app
        c = app.test_client()
        r = c.post("/runs/doesnotexist/calibrate-observed", data={})
        self.assertIn(r.status_code, (400, 404))
