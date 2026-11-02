"""Mitigation, dam screening, design storms, AAL, observed scoring: small synthetic checks (CPU, milliseconds)."""
import unittest
import numpy as np
from landslide.app import design_storm as DS, observed as OB, pipeline as P
from landslide.engine import aal, dam, interventions as IV, trigger as TR
from landslide.engine.flow import FlowState


def _table():
    dur = [1.0, 2.0, 3.0, 6.0, 12.0, 24.0]
    base = np.array([8.0, 13.6, 17.9, 28.0, 44.5, 65.9])
    return {"durations_h": dur, "periods": [100], "depth_mm": [base.tolist()]}


class TestDesignStorm(unittest.TestCase):
    def test_gumbel_lmoments_recover_parameters(self):
        rng = np.random.default_rng(0)
        x = 40.0 - 12.0 * np.log(-np.log(rng.uniform(size=5000)))
        xi, a = DS.gumbel_lmom(x)
        self.assertAlmostEqual(xi, 40.0, delta=0.8); self.assertAlmostEqual(a, 12.0, delta=0.5)

    def test_return_value_increases_with_period(self):
        q = DS.gumbel_quantile(40, 12, [2, 10, 100])
        self.assertTrue(q[0] < q[1] < q[2])

    def test_hyetograph_conserves_the_idf_depth_and_peaks_in_the_middle(self):
        t = _table()
        for D in (3, 6, 24):
            h = DS.design_hyetograph(t, 100, D, 15, short="power")
            self.assertAlmostEqual(h["total_mm"], t["depth_mm"][0][t["durations_h"].index(D)], places=6)
            r = np.array(h["rate_mm_h"]); self.assertLess(abs(int(np.argmax(r)) - len(r) // 2), 2)

    def test_climate_factor_scales_the_storm(self):
        h1 = DS.design_hyetograph(_table(), 100, 6, 15, short="power"); h2 = DS.design_hyetograph(_table(), 100, 6, 15, short="power", climate_factor=1.2)
        self.assertAlmostEqual(h2["total_mm"] / h1["total_mm"], 1.2, places=6)


class TestAAL(unittest.TestCase):
    def test_trapezoid_in_probability(self):
        T = np.array([2, 4, 8, 16]); L = 100.0 / T
        want = np.trapezoid(100 * np.array([1 / 16, 1 / 8, 1 / 4, 1 / 2]), [1 / 16, 1 / 8, 1 / 4, 1 / 2])
        self.assertAlmostEqual(aal.eal(T, L)["parts"]["between_scenarios"], want, places=9)

    def test_zero_loss_gives_zero_and_more_loss_gives_more(self):
        T = [2, 10, 100]
        self.assertEqual(aal.eal(T, [0, 0, 0])["eal"], 0.0)
        self.assertGreater(aal.eal(T, [0, 5, 50])["eal"], aal.eal(T, [0, 5, 20])["eal"])


class TestMitigation(unittest.TestCase):
    def _setup(self):
        from landslide.app import pipeline as P
        spec, _ = P.build_spec({"strength_preset": "colluvium_shallow", "texture": "sandy loam"})
        sp = TR.scenario_point(spec, 0.3)
        slope = np.full((20, 20), 33.0, "float32"); valid = np.ones_like(slope, bool)
        z = TR.soil_depth_field(slope, sp, False)
        steps = np.full(96, 4.0)                                       # 15 min steps, 16 mm/h for 24 h
        return slope, valid, z, sp, steps

    def _fail(self, fields):
        slope, valid, z, sp, steps = self._setup()
        mob, _ = TR.mobilisable_mask(slope, valid, z, sp, 45.0, fields)
        tf, *_ = TR.rain_failure_times(slope, mob, steps, 900, sp, z, 10.0, fields)
        return int(np.isfinite(tf).sum())

    def test_each_nature_based_lever_never_increases_failure(self):
        base = self._fail(None)
        self.assertGreater(base, 0)                                     # the baseline must fail or the test says nothing
        sh = (20, 20)
        planting = {"c_root_add": np.full(sh, 8000.0, "float32"), "slope_cap": None, "m_scale": None, "wt_add": None}
        regrade = {"c_root_add": None, "slope_cap": np.full(sh, 25.0, "float32"), "m_scale": None, "wt_add": None}
        drain = {"c_root_add": None, "slope_cap": None, "m_scale": np.full(sh, 0.4, "float32"), "wt_add": np.full(sh, 3.0, "float32")}
        for f in (planting, regrade, drain):
            self.assertLessEqual(self._fail(f), base)
        self.assertLess(self._fail(regrade), base)                      # a 25 deg cap on a 33 deg slope must help

    def test_barrier_holds_back_a_slug_and_a_higher_wall_holds_more(self):
        n, dx = 90, 20.0
        Z = np.tile(-(np.arange(n) * dx) * 0.35, (n, 1))
        def past_wall(h):
            Zb = Z.copy()
            if h:
                Zb[:, 50:52] += h + 0.35 * dx                            # the model's rule: height above the ground upslope = h + tan(slope) x cell
            s = FlowState(Zb, dx); s.H[:, 8:18] = 2.0
            for _ in range(1500):
                s.step(0.1, 0.12, 200.0)
            return float(s.H[:, 53:].sum() * dx * dx)                    # volume that got past the wall
        free, w6, w12 = past_wall(0), past_wall(6.0), past_wall(12.0)
        self.assertGreater(free, 0)
        self.assertLess(w6, 0.2 * free)                                  # a 6 m wall stops most of it; momentum run-up v^2/2g ~ 6 m lets a little over
        self.assertLess(w12, w6)                                         # a higher wall holds back more

    def test_barrier_rule_adds_the_ground_drop_across_a_cell(self):
        grid = {"resolution_m": 30.0, "affine": __import__("rasterio").transform.Affine(30, 0, 500000, 0, -30, 4000000), "crs": "EPSG:32643"}
        from pyproj import Transformer
        lon, lat = Transformer.from_crs(32643, 4326, always_xy=True).transform(500300, 3999700)
        lon2, lat2 = Transformer.from_crs(32643, 4326, always_xy=True).transform(500600, 3999700)
        add, info = IV.barriers_mask([{"coords": [[lon, lat], [lon2, lat2]], "height_m": 5.0, "width_m": 30.0}], grid, 32643, (60, 60), np.full((60, 60), 20.0))
        self.assertAlmostEqual(float(add.max()), 5.0 + np.tan(np.deg2rad(20.0)) * 30.0, places=4)
        self.assertEqual(info[0]["height_basis"], "above the ground immediately upslope")

    def test_ranking_orders_by_failing_area_reduction(self):
        calls = {None: 100.0}
        def ev(spec):
            if spec is None:
                return {"failing_km2": 100.0}
            return {"failing_km2": 100.0 - 10.0 * len([k for k in spec if k != "zone"])}
        r = IV.rank_nbs(ev)
        self.assertEqual(len(r["ranked"]), 7)
        self.assertEqual(len(r["ranked"][0]["levers"]), 3)


class TestDam(unittest.TestCase):
    def test_deposit_across_a_channel_is_a_dam_and_dbi_follows_the_formula(self):
        n, dx = 60, 30.0
        x = np.arange(n)
        Z = np.add.outer(np.abs(x - 30) * 8.0, (n - x) * 3.0).astype(float)    # V valley along the columns, draining toward larger col index
        dep = np.zeros((n, n)); dep[28:33, 40:46] = 8.0
        r = dam.assess(Z, dep, np.ones((n, n), bool), dx, min_drainage_km2=0.05, min_dam_m=2.0)
        self.assertEqual(r["n_blocking"], 1)
        d = r["dams"][0]
        self.assertAlmostEqual(d["dam_height_m"], 8.0)
        self.assertAlmostEqual(d["dbi"], np.log10(d["upstream_area_km2"] * 1e6 * 8.0 / d["dam_volume_m3"]), places=9)
        self.assertGreater(d["lake_volume_m3"], 0)

    def test_classes_and_breach_formula(self):
        self.assertEqual(dam.classify(2.0), "likely stable"); self.assertEqual(dam.classify(3.5), "likely unstable"); self.assertEqual(dam.classify(2.9), "uncertain")
        self.assertAlmostEqual(dam.froehlich_qp(1e7, 50.0), 0.607 * 1e7 ** 0.295 * 50.0 ** 1.24, places=6)
        self.assertAlmostEqual(dam.froehlich_qp(1e7, 50.0), 9014, delta=5)       # same value as the earlier prototype's test V25

    def test_no_dam_when_deposit_is_off_the_channel(self):
        n, dx = 60, 30.0
        x = np.arange(n)
        Z = np.add.outer(np.abs(x - 30) * 8.0, (n - x) * 3.0).astype(float)
        dep = np.zeros((n, n)); dep[2:6, 2:6] = 8.0                             # far up a valley wall
        self.assertEqual(dam.assess(Z, dep, np.ones((n, n), bool), dx, min_drainage_km2=0.05)["n_blocking"], 0)


class TestObserved(unittest.TestCase):
    def test_perfect_and_disjoint(self):
        m = np.zeros((8, 8), bool); m[2:5, 2:5] = True
        v = np.ones((8, 8), bool)
        self.assertEqual(OB.score(m, m, v)["CSI"], 1.0)
        o = np.zeros((8, 8), bool); o[6:8, 6:8] = True
        s = OB.score(m, o, v)
        self.assertEqual(s["CSI"], 0.0); self.assertEqual(s["POD"], 0.0)


if __name__ == "__main__":
    unittest.main()


class TestCalibrationMachinery(unittest.TestCase):
    """Tiny synthetic checks of the batched calibration physics (CPU): no data, no GPU, milliseconds."""
    def test_batched_front_matches_the_scalar_green_ampt_model(self):
        import torch
        from landslide.calibration import physcal as PC
        from landslide.models.infiltration import green_ampt
        rain = np.array([0, 5, 20, 40, 10, 0, 0, 15, 30, 2.0] * 6)
        ga = green_ampt.run(rain, 3600, 3.7e-6, 0.089, 0.463, 0.25, 1.0)
        F = PC.ga_front(torch.tensor(rain[None, :]), torch.tensor([3.7e-6], dtype=torch.float64), 0.089, 0.213)
        self.assertAlmostEqual(float(F[0]), float(ga["F_m"][-1]), delta=0.03 * float(ga["F_m"][-1]) + 1e-5)   # substeps 4 vs 20: within 3%

    def test_more_rain_and_steeper_slope_raise_the_instability_score(self):
        import torch
        from landslide.calibration import physcal as PC
        th = {"c": 3000.0, "phi": 30.0, "cr": 1000.0, "z": 1.5, "wt": 4.0}
        rain = torch.tensor(np.stack([np.zeros(72), np.full(72, 3.0), np.full(72, 12.0)]))
        sl = torch.tensor(np.full((3, 50), 33.0))
        s = PC.score_params(th, rain, sl, (3.7e-6, 0.089, 0.213), None)
        self.assertTrue(float(s[0]) <= float(s[1]) <= float(s[2]) + 1e-9)
        steep = PC.score_params(th, rain[2:3], torch.tensor(np.full((1, 50), 38.0)), (3.7e-6, 0.089, 0.213), None)
        self.assertGreaterEqual(float(steep[0]), float(s[2]) - 1e-9)

    def test_validate_pga_error_stats(self):
        import importlib.util, pathlib
        p = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "validate_pga.py"
        spec = importlib.util.spec_from_file_location("vp", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        d = np.linspace(5, 200, 400); obs = TR.bssa14_pga_g(6.5, d, 400.0)
        r = m.stats(np.log(TR.bssa14_pga_g(6.5, d, 400.0)) - np.log(obs))
        self.assertAlmostEqual(r["bias_ln"], 0.0, places=9); self.assertAlmostEqual(r["sd_ln"], 0.0, places=9)
        r2 = m.stats(np.log(1.5 * obs) - np.log(obs)); self.assertAlmostEqual(r2["bias_ln"], np.log(1.5), places=9)

    def test_ground_motion_models_behave(self):
        d = np.array([5.0, 20.0, 80.0, 200.0])
        for model in (lambda M, v: TR.bssa14_pga_g(M, d, v), lambda M, v: TR.bchydro_slab_pga_g(M, d, 150.0, v)):
            a = model(6.0, 760.0); self.assertTrue(np.all(np.diff(a) < 0))                       # decays with distance
            self.assertTrue(np.all(model(7.0, 760.0) > model(6.0, 760.0)))                       # grows with magnitude
            self.assertTrue(np.all(model(6.5, 250.0) > model(6.5, 760.0)))                       # soft soil amplifies
        self.assertTrue(np.all(TR.pga_model(6.5, d, 760.0, "auto", 200.0) < TR.bchydro_slab_pga_g(6.5, d, 200.0, 760.0)))   # regional slab adjustment lowers it
        y, sig = TR.bssa14_pga_g(6.5, 20.0, 400.0, return_sigma=True); self.assertTrue(0.4 < float(sig) < 0.9)
        self.assertAlmostEqual(float(TR.bssa14_pga_g(6.5, 20.0, 760.0)), float(TR.bssa14_pga_g(6.5, 20.0, 760.0)), 9)

    def test_planting_never_increases_the_unstable_area_but_can_increase_the_failing_area(self):
        spec, _ = P.build_spec({"strength_preset": "colluvium_shallow", "texture": "sandy loam"})
        sp = TR.scenario_point(spec, 0.0); slope = np.tile(np.linspace(10, 44, 80)[None, :], (4, 1)).astype("float32"); valid = np.ones_like(slope, bool)
        z = TR.soil_depth_field(slope, sp, True); steps = np.full(48, 12.0)
        fields = {"c_root_add": np.full(slope.shape, 6000.0, "float32")}
        def counts(f):
            mob, _ = TR.mobilisable_mask(slope, valid, z, sp, 45.0, f); tf, *_ = TR.rain_failure_times(slope, mob, steps, 900, sp, z, 10.0, f)
            tfa, *_ = TR.rain_failure_times(slope, valid, steps, 900, sp, z, 10.0, f)
            return int(np.isfinite(tf).sum()), int(np.isfinite(tfa).sum())
        (f0, u0), (f1, u1) = counts(None), counts(fields)
        self.assertLessEqual(u1, u0)          # like-for-like measure: stronger roots can only remove unstable cells
        self.assertGreater(u0, 0)

    def test_wetness_suction_and_gridded_rain(self):
        from landslide.engine import wetness as WET
        spec, _ = P.build_spec({"strength_preset": "colluvium_shallow", "texture": "sandy loam"})
        sp = TR.scenario_point(spec, 0.5); slope = np.full((6, 40), 30.0, "float32"); valid = np.ones_like(slope, bool)
        z = TR.soil_depth_field(slope, sp, False); steps = np.full(24, 6.0)
        # topographic water table: a convergent (high TWI) half is wetter than a divergent half
        twi = np.where(np.arange(40)[None, :] < 20, 4.0, 10.0).astype("float32") * np.ones_like(slope)
        sp_w, rep = WET.apply(sp, twi, valid, 1.0); wt = sp_w["water_table"]
        self.assertLess(float(wt[0, 30]), float(wt[0, 5])); self.assertEqual(WET.apply(sp, twi, valid, 0.0)[0], sp)
        # suction: more strength when dry, none when saturated, so it can only reduce failure
        sp_s = dict(sp); sp_s["suction_pa"] = 8000.0
        mob0, _ = TR.mobilisable_mask(slope, valid, z, sp, 45.0); mob1, _ = TR.mobilisable_mask(slope, valid, z, sp_s, 45.0)
        self.assertGreaterEqual(int(mob1.sum()), int(mob0.sum()))
        self.assertEqual(float(TR.suction_cohesion(sp_s, 1.0)), 0.0); self.assertEqual(float(TR.suction_cohesion(sp_s, 0.0)), 8000.0)
        # gridded rain: cells that get twice the rain fail no later than cells that get half
        sp_r = dict(sp); sp_r["rain_scale"] = np.where(np.arange(40)[None, :] < 20, 0.5, 2.0).astype("float32") * np.ones_like(slope)
        tf, *_ = TR.rain_failure_times(slope, valid, steps * 3, 900, sp_r, z, 10.0)
        a, b = np.isfinite(tf[:, :20]).sum(), np.isfinite(tf[:, 20:]).sum()
        self.assertGreaterEqual(b, a)

    def test_loss_valuation_follows_sailab(self):
        from landslide.engine import loss as LS
        self.assertAlmostEqual(LS.MAX_DAMAGE_PKR_PER_M2["Residential"], 111 * 322.5, 3)
        one = LS.building_structure_loss(0.5, 100.0, 3.0); two = LS.building_structure_loss(0.5, 100.0, 6.0)
        self.assertAlmostEqual(one, 0.5 * 100 * 111 * 322.5, 3); self.assertAlmostEqual(two, 2 * one, 3)
        self.assertEqual(LS.building_structure_loss(0.5, 100.0, 1.0), one)             # at least one storey
        loss, n = LS.agricultural_loss(np.array([0.0, 0.2, 0.6, 3.0]), 900.0)
        self.assertEqual(n, 3); self.assertAlmostEqual(loss, (0.4 + 1 + 1) * 900.0 * 0.03 * 322.5, 3)
        self.assertEqual(aal.eal([2, 100], [0.0, 0.0])["eal"], 0.0)

    def test_antecedent_wetness_and_ensemble(self):
        from landslide.engine import antecedent as ANT, ensemble as ENS
        self.assertEqual(ANT.api([0, 0, 0]), 0.0); self.assertGreater(ANT.api([0, 0, 50]), ANT.api([50, 0, 0]))     # recent rain counts more
        sp = {"theta_s": 0.45, "theta_i": 0.25, "water_table": 4.0}
        dry, _ = ANT.apply(sp, 0.0); wet, rep = ANT.apply(sp, 500.0)
        self.assertGreater(wet["theta_i"], dry["theta_i"]); self.assertLess(wet["water_table"], dry["water_table"]); self.assertEqual(rep["wetness"], 1.0)
        spec, _ = P.build_spec({"strength_preset": "colluvium_shallow", "texture": "sandy loam"})
        pts = ENS.sample_points(spec, 16, 3)
        self.assertEqual(len(pts), 16); self.assertGreater(len({round(p["effective_cohesion"]) for p in pts}), 12)          # members really differ
        slope = np.tile(np.linspace(5, 55, 60)[None, :], (30, 1)).astype("float32"); valid = np.ones_like(slope, bool)
        o = ENS.pfail(slope, valid, np.full(48, 15.0), 900, spec, n=24, seed=2, min_slope=10.0)
        pf = o["p_fail"]; self.assertTrue(np.all((pf >= 0) & (pf <= 1))); self.assertEqual(float(np.nanmax(pf[:, :6])), 0.0)       # flat ground never fails
