import unittest
import numpy as np
from landslide.engine import census as CEN, run as R


class TestCensus(unittest.TestCase):
    def test_lookup_and_shares(self):
        k = CEN.districts_for([71.5, 73.05, 74.31], [30.2, 33.7, 35.92])
        self.assertEqual(k[0], "multan"); self.assertEqual(k[1], "islamabad"); self.assertEqual(k[2], "gilgit")
        mix, known = CEN.housing_mix(k[0]); self.assertTrue(known); self.assertAlmostEqual(sum(mix), 1.0, 6)
        mix_g, known_g = CEN.housing_mix(k[2]); self.assertFalse(known_g); self.assertAlmostEqual(sum(mix_g), 1.0, 6)     # Gilgit has no census row: national mean, flagged
        self.assertGreater(CEN.hh_size(k[0])[0], 3.0)

    def test_kacha_buildings_are_damaged_more(self):
        for h, v in ((0.5, 2.0), (1.5, 5.0), (3.0, 8.0)):
            pak = R.building_damage(h, v, 100.0, (1, 0, 0))[0]; kac = R.building_damage(h, v, 100.0, (0, 0, 1))[0]; mix = R.building_damage(h, v, 100.0, (0.5, 0, 0.5))[0]
            self.assertGreaterEqual(kac, pak); self.assertTrue(min(pak, kac) - 1e-9 <= mix <= max(pak, kac) + 1e-9)
        self.assertEqual(R.building_damage(0.1, 1.0, 100.0, (0, 0, 1))[0], 0.0)           # no flow over the threshold: no damage in any class

    def test_population_fallback_from_district_density(self):
        from landslide.app import rasters
        g = rasters.make_grid((71.40, 30.10, 71.45, 30.15), 32642, 90.0); v = np.ones((g["height"], g["width"]), bool)
        pop, share = CEN.population_field(g, v)
        self.assertGreater(share, 0.9); self.assertGreater(float(np.nansum(pop)), 1000)


if __name__ == "__main__":
    unittest.main()
