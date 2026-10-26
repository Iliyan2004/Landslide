"""§6.2 physics checks + analytic verification. Run: python -m unittest discover -s tests -v (from backend/)."""
import unittest
import numpy as np
from landslide.models.stability import infinite_slope as I, bishop as B, ensemble as E
from landslide.models.infiltration import green_ampt as GA, api_index as API
from landslide.models.seismic import newmark as N, rock_kinematics as RK
from landslide.models.runout import empirical as RE, rockfall as RF
from landslide.models.sediment import hillslope_channel as S
from landslide.errors import GateError


class TestInfiniteSlope(unittest.TestCase):
    def test_dry_cohesionless_phi_equals_beta(self):
        self.assertAlmostEqual(float(I.factor_of_safety(30, 1.5, 0, 30, 18e3)), 1.0, places=9)

    def test_saturated_closed_form(self):
        exp = (1 - 9806.65 / 18e3) * np.tan(np.deg2rad(30)) / np.tan(np.deg2rad(30))
        self.assertAlmostEqual(float(I.factor_of_safety(30, 1.5, 0, 30, 18e3, m=1)), exp, places=9)

    def test_monotonic_pore_pressure_and_cohesion(self):
        m = np.linspace(0, 1, 21)
        fs = I.factor_of_safety(30, 2, 3e3, 32, 18e3, m=m)
        self.assertTrue(np.all(np.diff(fs) <= 1e-12))
        c = np.linspace(0, 2e4, 21)
        self.assertTrue(np.all(np.diff(I.factor_of_safety(30, 2, c, 32, 18e3, m=0.5)) >= -1e-12))

    def test_invalid_and_flat(self):
        self.assertTrue(np.isnan(I.factor_of_safety(20, 0, 0, 30, 18e3)))      # z=0 invalid, not FS=0
        self.assertTrue(np.isinf(I.factor_of_safety(0.0, 1.5, 0, 30, 18e3)))   # flat = non-failure

    def test_critical_m_gives_fs_one(self):
        mc = I.critical_m(35, 2, 4e3, 33, 18e3)
        self.assertAlmostEqual(float(I.factor_of_safety(35, 2, 4e3, 33, 18e3, m=mc)), 1.0, places=6)

    def test_unsat_refuses_positive_pressure(self):
        with self.assertRaises(ValueError):
            I.unsaturated_shear_strength(0, 1e4, 0, 5e3, 30, 15)


class TestHydrology(unittest.TestCase):
    def test_zero_ks_absorbs_nothing_and_dry_stays_dry(self):
        r = GA.run(np.full(10, 20.0), 3600, 0.0, 0.2, 0.45, 0.2, 2.0, m0=0.0)
        self.assertEqual(r["infiltration_m"].sum(), 0.0)
        self.assertEqual(r["m"].max(), 0.0)

    def test_no_rain_no_pressure(self):
        r = GA.run(np.zeros(10), 3600, 1e-5, 0.2, 0.45, 0.2, 2.0, m0=0.0)
        self.assertEqual(r["m"].max(), 0.0)

    def test_mass_balance_and_m_bounded(self):
        r = GA.run(np.r_[np.full(12, 15.0), np.zeros(6)], 3600, np.array([1e-6, 1e-5, 1e-4]), 0.2, 0.45, 0.2, 1.5)
        self.assertLess(np.abs(r["mass_balance_residual_m"]).max(), 1e-12)
        self.assertTrue(r["m"].min() >= 0 and r["m"].max() <= 1)
        self.assertTrue(np.all(np.diff(r["F_m"], axis=0) >= -1e-15))

    def test_negative_rain_rejected(self):
        with self.assertRaises(ValueError):
            GA.run([-1.0], 3600, 1e-5, 0.2, 0.45, 0.2, 1)

    def test_api_and_rolling(self):
        a = API.antecedent_precipitation_index([10, 0, 0], k=0.5)
        np.testing.assert_allclose(a, [10, 5, 2.5])
        rs = API.rolling_sum(np.ones(5), 3)
        self.assertTrue(np.isnan(rs[:2]).all()); np.testing.assert_allclose(rs[2:], 3)


class TestEnsemble(unittest.TestCase):
    spec = {"soil_depth": {"min": 1, "max": 3}, "effective_cohesion": {"min": 2e3, "max": 8e3},
            "friction_angle": {"min": 28, "max": 38}, "hydraulic_conductivity": {"min": 1e-6, "max": 1e-4},
            "water_table": {"min": 2, "max": 6}}

    def test_rain_lowers_fs_and_reproducible(self):
        rain = np.r_[np.zeros(6), np.full(24, 8.0)]
        a = E.run_point(32, rain, 3600, self.spec, n=100, seed=3)
        b = E.run_point(32, rain, 3600, self.spec, n=100, seed=3)
        np.testing.assert_array_equal(a["min_fs"], b["min_fs"])
        dry = E.run_point(32, np.zeros(30), 3600, self.spec, n=100, seed=3)
        self.assertLessEqual(np.median(a["min_fs"]), np.median(dry["min_fs"]) + 1e-12)
        self.assertTrue(a["status"]["not_for_engineering_design"])

    def test_unknown_params_rejected_not_defaulted(self):
        bad = dict(self.spec); bad["soil_depth"] = None
        with self.assertRaises(GateError):
            E.run_point(30, np.zeros(5), 3600, bad)

    def test_implausible_range_rejected(self):
        bad = dict(self.spec); bad["friction_angle"] = {"min": 28, "max": 80}
        with self.assertRaises(GateError):
            E.run_point(30, np.zeros(5), 3600, bad)


class TestSeismic(unittest.TestCase):
    def test_ky_makes_fs_one_and_static_equivalence(self):
        ky = N.yield_coefficient(30, 2, 5e3, 35, 18e3, m=0.3)
        self.assertAlmostEqual(float(N.pseudostatic_fs(30, 2, 5e3, 35, 18e3, ky, m=0.3)), 1.0, places=9)
        self.assertAlmostEqual(float(N.pseudostatic_fs(30, 2, 5e3, 35, 18e3, 0, m=0.3)),
                               float(I.factor_of_safety(30, 2, 5e3, 35, 18e3, m=0.3)), places=9)

    def test_newmark_analytic_and_no_exceedance(self):
        dt = 1e-3; a = np.full(2000, 3.0)
        d, _ = N.newmark_displacement(a, dt, 1.0)
        self.assertAlmostEqual(d, 0.5 * 2.0 * 2.0**2, places=6)
        self.assertEqual(N.newmark_displacement(a, dt, 5.0), (0.0, 0.0))

    def test_jibson_zero_when_ay_ge_pga(self):
        self.assertEqual(float(N.jibson2007_displacement_cm(0.3, 0.2)), 0.0)
        self.assertGreater(float(N.jibson2007_displacement_cm(0.1, 0.3)), 0.0)

    def test_planar_kinematics(self):
        self.assertTrue(RK.planar_feasible(40, 180, 60, 180, 30))
        self.assertFalse(RK.planar_feasible(40, 180, 60, 270, 30))      # off-azimuth
        self.assertFalse(RK.planar_feasible(25, 180, 60, 180, 30))      # below friction


class TestBishop(unittest.TestCase):
    def test_phi0_matches_closed_form(self):
        rng = np.random.default_rng(0)
        b = rng.uniform(0.5, 1.5, 12); W = rng.uniform(50, 150, 12); a = rng.uniform(0.05, 0.9, 12)
        r = B.bishop_fs(b, W, a, 20.0, 0.0)
        self.assertTrue(r["converged"])
        self.assertAlmostEqual(r["fs"], float(np.sum(20.0 * b / np.cos(a)) / np.sum(W * np.sin(a))), places=9)

    def test_circle_search_finds_stable_homogeneous_slope(self):
        x = np.linspace(0, 40, 81); z = np.where(x < 10, 20, np.where(x < 20, 20 - (x - 10), 10))
        best = B.search_circles(x, z, 18e3, 15e3, 25, [5, 10, 15], [25, 30, 35], [12, 15, 18, 22])
        self.assertIsNotNone(best); self.assertTrue(best["converged"]); self.assertGreater(best["fs"], 0)


class TestRunout(unittest.TestCase):
    def test_voellmy_stop_distance(self):
        b = np.deg2rad(5); mu = 0.3
        s = np.linspace(0, 5000, 501) * np.cos(b); z = -np.linspace(0, 5000, 501) * np.sin(b)
        r = RE.voellmy_profile(s, z, mu, 1e12, 2.0, v0=10.0, dt=0.01)
        self.assertAlmostEqual(r["stop_distance_m"], 100 / (2 * 9.80665 * (mu * np.cos(b) - np.sin(b))), places=4)

    def test_envelope_monotonic_in_alpha_and_needs_source(self):
        y, x = np.mgrid[0:40, 0:80]; dem = 300 - 3.0 * x + 0.0 * y
        src = np.zeros(dem.shape, bool); src[20, 2] = True
        r_lo, _, L_lo = RE.reach_envelope(dem, 30, 30, src, 10)
        r_hi, _, L_hi = RE.reach_envelope(dem, 30, 30, src, 20)
        self.assertTrue(np.all(r_hi <= r_lo)); self.assertGreaterEqual(L_lo, L_hi)
        with self.assertRaises(GateError):
            RE.ensemble_envelope(dem, 30, 30, np.zeros_like(src), 1e4, (10, 20))

    def test_rockfall_energy_and_rebound(self):
        X = np.array([-100, 100.]); Z = np.zeros(2)
        r = RF.simulate(X, Z, ["a"], {"a": (0.5, 0.9)}, 0, 10.0, v_stop=0.01, max_bounces=1)
        self.assertAlmostEqual(r["impacts"][0][1], 1000 * 9.80665 * 10, places=3)
        r2 = RF.simulate(X, Z, ["a"], {"a": (0.5, 0.9)}, 0, 10.0, v_stop=0.01, max_bounces=2)
        self.assertAlmostEqual(r2["impacts"][1][1], 0.25 * r2["impacts"][0][1], places=3)   # KE after e_n=0.5 -> e^2

    def test_mass_balance(self):
        self.assertEqual(RE.mass_balance_residual(100, 20, 90, 30), 0)


class TestSediment(unittest.TestCase):
    def test_below_threshold_zero_and_nonnegative(self):
        self.assertEqual(float(S.mpm_bedload_per_width(0.5, 0.02)), 0.0)
        self.assertGreater(float(S.mpm_bedload_per_width(20.0, 0.02)), 0.0)

    def test_mpm_closed_form(self):
        tau, d = 40.0, 0.02
        th = tau / (1650 * 9.80665 * d)
        exp = 8 * (th - 0.047) ** 1.5 * np.sqrt(1.65 * 9.80665 * d**3)
        self.assertAlmostEqual(float(S.mpm_bedload_per_width(tau, d)), exp, places=12)

    def test_width_required_and_nodata_wet_only(self):
        with self.assertRaises(ValueError): S.total_bedload(1e-3, None)
        self.assertTrue(np.isnan(S.bed_shear_manning(0.03, 2.0, 0.0)))

    def test_rusle_and_assumption_flag(self):
        r = S.rusle(100, 0.3, 5, 0.1)
        self.assertAlmostEqual(r["A_t_ha_yr"], 15.0); self.assertIn("P=1 (unknown practice)", r["assumptions"])

    def test_exner_disabled(self):
        with self.assertRaises(NotImplementedError): S.exner_step(0, 0, 1)


if __name__ == "__main__":
    unittest.main()
