import unittest, datetime as dt
import numpy as np, pandas as pd
from landslide.data.preprocessing import aoi, soil, inventory, forcing
from landslide.data.fetchers import sources as S
from landslide.errors import GateError

SQ = {"type": "Polygon", "coordinates": [[[74.0, 35.0], [74.2, 35.0], [74.2, 35.2], [74.0, 35.2], [74.0, 35.0]]]}
BOW = {"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]}


class TestAOI(unittest.TestCase):
    def test_valid_and_hash_stable(self):
        bbox, area, w = aoi.validate_geojson(SQ)
        self.assertEqual(bbox, (74.0, 35.0, 74.2, 35.2)); self.assertGreater(area, 100); self.assertEqual(w, [])
        self.assertEqual(aoi.aoi_sha256(SQ), aoi.aoi_sha256(SQ))

    def test_self_intersection_rejected(self):
        with self.assertRaises(GateError): aoi.validate_geojson(BOW)

    def test_utm_and_zone_cross_warning(self):
        self.assertEqual(aoi.utm_epsg(74.3, 35.9), 32643)
        _, w = aoi.select_analysis_crs((71.0, 30.0, 78.0, 31.0)); self.assertTrue(w)

    def test_grid_spec_snaps_outward(self):
        g = aoi.grid_spec((100.4, 200.4, 1000.1, 900.7), 30, 32643)
        x0, res, _, y1, _, _ = g["transform"]
        self.assertEqual(x0 % 30, 0); self.assertEqual(y1 % 30, 0)
        self.assertGreaterEqual(x0 + g["width"] * 30, 1000.1)


class TestSoil(unittest.TestCase):
    def test_integrate_respects_layers(self):
        self.assertAlmostEqual(soil.integrate_profile([10, 20, 30, 40, 50, 60], 15), (10 * 5 + 20 * 10) / 15)

    def test_texture_and_priors_flagged_unmeasured(self):
        self.assertEqual(soil.usda_texture(90, 5, 5), "sand")
        self.assertEqual(soil.usda_texture(20, 20, 60), "clay")
        p = soil.hydraulic_priors("loam"); self.assertFalse(p["measured"]); self.assertLess(p["hydraulic_conductivity"]["min"], p["hydraulic_conductivity"]["max"])


class TestInventory(unittest.TestCase):
    def test_standardise_roles_and_positives(self):
        df = pd.DataFrame({"lon": [74.1, 74.1001, 74.5], "lat": [35.1, 35.1001, 35.5], "hazard_subtype": ["slide"] * 3,
                           "occurrence_utc": ["2022-07-01"] * 3, "feature_role": ["source_scar", "source_scar", "runout_deposit"],
                           "position_uncertainty_m": [50, 50, 50]})
        s = inventory.standardise(df, "test"); d = inventory.dedupe(s)
        self.assertEqual(len(d), 2); self.assertEqual(len(inventory.susceptibility_positives(d)), 1)
        with self.assertRaises(ValueError): inventory.standardise(df.assign(feature_role="bogus"), "t")


class TestForcing(unittest.TestCase):
    def test_qc(self):
        t = pd.date_range("2025-07-01", periods=48, freq="1h")
        s, meta = forcing.prepare_hourly(t, np.ones(48), "x", "1", "now"); self.assertEqual(meta["timezone"], "UTC")
        with self.assertRaises(GateError): forcing.prepare_hourly(t, -np.ones(48), "x", "1", "now")
        with self.assertRaises(GateError): forcing.event_window(s, "2025-07-02", "2025-07-02 12:00", 30)


class TestFetcherURLs(unittest.TestCase):
    def test_dem_tiles(self):
        n = S.copernicus_dem_tile_names((74.1, 35.1, 74.9, 35.9))
        self.assertEqual(len(n), 1); self.assertIn("N35_00_E074_00", n[0])

    def test_worldcover_tile(self):
        u = S.worldcover_tile_urls((74.1, 35.1, 74.9, 35.9)); self.assertEqual(len(u), 1); self.assertIn("N33E072", u[0])

    def test_usgs_and_chirps(self):
        self.assertIn("minmagnitude=5", S.usgs_event_query_url("2020-01-01", "2021-01-01", (60, 20, 80, 40), 5))
        self.assertTrue(S.chirps_daily_url(dt.date(2022, 7, 5)).endswith("chirps-v2.0.2022.07.05.tif.gz"))

    def test_missing_credentials_is_explicit(self):
        from landslide.errors import SourceUnavailable
        import os; os.environ.pop("CDSAPI_KEY", None)
        with self.assertRaises(SourceUnavailable): S.Era5Land().fetch((74, 35, 75, 36), "/tmp/x", year=2022, month=7)


if __name__ == "__main__":
    unittest.main()
