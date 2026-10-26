"""Runout engine checks (the same analytic guards as docs/VALIDATION_REPORT V4-V7) on CPU and GPU, plus trigger physics."""
import unittest
import numpy as np
from landslide.engine.flow import FlowState
from landslide.engine import trigger as TR


def _slope_bed(n, dx, tan):
    return np.tile(-(np.arange(n) * dx) * tan, (n, 1))


class TestFlow(unittest.TestCase):
    def test_mass_conserved_in_closed_domain(self):
        n = 80; s = FlowState(np.zeros((n, n)), 20.0)
        r = np.zeros((n, n)); r[35:45, 35:45] = 3.0; s.add_release(r); s.H += 0.0
        s.Z += r                                    # put the bed back so the slug has a gradient to spread under
        v0 = s.volume()
        for _ in range(600):
            s.step(0.1, 0.0, 400.0)
        self.assertLess(abs(s.volume() - v0) / v0, 1e-9)
        self.assertGreater((s.H > 0.05).sum(), 100)

    def test_lake_at_rest_is_well_balanced(self):
        rng = np.random.default_rng(1); Z = rng.uniform(0, 2, (60, 60))
        s = FlowState(Z, 20.0); s.H = np.maximum(3.0 - Z, 0)
        for _ in range(200):
            s.step(0.2, 0.0, 400.0)
        self.assertLess(max(abs(s.Qx).max(), abs(s.Qy).max()), 1e-9)

    def test_steady_speed_matches_voellmy(self):
        n, dx = 160, 20.0
        s = FlowState(_slope_bed(n, dx, 0.5), dx); s.H[:, 5:120] = 1.5
        for _ in range(500):
            s.step(0.1, 0.2, 400.0)
        v = s.V[n // 2, 40:90].mean(); th = np.arctan(0.5)
        analytic = np.sqrt(400 * 1.5 * (0.5 - 0.2 * np.cos(th)))
        self.assertLess(abs(v - analytic) / analytic, 0.05)         # dt=0.1 s: first-order splitting error ~2%

    def test_rests_below_friction_slope(self):
        n, dx = 100, 20.0
        s = FlowState(_slope_bed(n, dx, 0.15), dx); s.H[:, 5:50] = 1.5
        for _ in range(100):
            s.step(0.1, 0.2, 400.0)
        self.assertLess(abs(s.Qx[:, 15:40]).max(), 1e-9)           # interior at rest (the front edge may slump briefly)

    def test_entrainment_moves_bed_to_flow_without_creating_mass(self):
        n, dx = 100, 20.0
        s = FlowState(_slope_bed(n, dx, 0.5), dx); s.H[:, 5:30] = 3.0; s.ero[:] = 1.0
        z0 = s.Z.sum(); h0 = s.H.sum()
        for _ in range(300):
            s.step(0.1, 0.12, 200.0, entrain=True)
        self.assertGreater(s.ent_vol[0], 0)
        self.assertAlmostEqual((s.H.sum() - h0) + (s.Z.sum() - z0), 0.0, delta=1e-6 * h0)

    def test_gpu_matches_cpu(self):
        import torch
        if not torch.cuda.is_available():
            self.skipTest("no CUDA")
        from landslide.engine.flow_torch import FlowStateGPU
        rng = np.random.default_rng(0); n = 120
        Z = np.tile(np.linspace(0, 300, n)[:, None], (1, n)) + rng.normal(0, .5, (n, n))
        r = np.zeros((n, n)); r[30:50, 30:90] = 3.0
        a = FlowState(Z, 30.0); a.add_release(r)
        try:
            b = FlowStateGPU(Z, 30.0, compile=False); b.add_release(r)
        except Exception as e:                      # shared GPU may be out of memory
            self.skipTest(f"GPU unavailable: {str(e)[:60]}")
        for _ in range(80):
            a.step(0.1, 0.12, 200.0, lam=0.6)
        b.advance(0.1, 80, 0.12, 200.0, lam=0.6)
        self.assertLess(np.abs(a.H - b.H.cpu().numpy()).max(), 1e-3)


class TestTrigger(unittest.TestCase):
    def test_joyner_boore_decays_with_distance_and_grows_with_magnitude(self):
        self.assertGreater(TR.jb81_pga_g(7.0, 5), TR.jb81_pga_g(7.0, 50))
        self.assertGreater(TR.jb81_pga_g(7.0, 20), TR.jb81_pga_g(6.0, 20))
        self.assertAlmostEqual(float(TR.jb81_pga_g(6.0, 0)), 10 ** (-1.02 + 0.249 * 6 - np.log10(7.3) - 0.00255 * 7.3), places=9)

    def test_wells_coppersmith_length(self):
        self.assertAlmostEqual(TR.rupture_length_km(7.0), 10 ** (-2.44 + 0.59 * 7.0), places=9)

    def test_failure_time_is_monotone_in_rain(self):
        from landslide.app import pipeline as P
        spec, _ = P.build_spec({"strength_preset": "colluvium_shallow", "texture": "sandy loam"})
        sp = TR.scenario_point(spec, 0.3)
        slope = np.full((5, 5), 35.0, "float32"); valid = np.ones((5, 5), bool); z = TR.soil_depth_field(slope, sp, False)
        light, *_ = TR.rain_failure_times(slope, valid, np.full(96, 1.0), 900, sp, z)
        heavy, *_ = TR.rain_failure_times(slope, valid, np.full(96, 15.0), 900, sp, z)
        self.assertTrue(np.isinf(light).all() or np.isfinite(heavy).all())
        if np.isfinite(light).any():
            self.assertLessEqual(heavy.min(), light.min())

    def test_mobilisable_excludes_rock_and_unstable_dry(self):
        from landslide.app import pipeline as P
        spec, _ = P.build_spec({"strength_preset": "weak_clayey"}); sp = TR.scenario_point(spec, 0.0)
        slope = np.array([[10, 30, 50, 70]], "float32"); v = np.ones_like(slope, bool); z = TR.soil_depth_field(slope, sp, False)
        m, st = TR.mobilisable_mask(slope, v, z, sp, 45.0)
        self.assertFalse(m[0, 2] or m[0, 3])
        self.assertEqual(st["cells_rock_too_steep"], 2)


if __name__ == "__main__":
    unittest.main()
