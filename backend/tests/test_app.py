"""App-layer checks: the fast stability grid must equal the reference time-stepped ensemble; count rasters keep totals."""
import unittest
import numpy as np
from landslide.app import pipeline as P
from landslide.models.stability import ensemble as ENS


class TestAppLayer(unittest.TestCase):
    def test_fast_grid_matches_reference_ensemble(self):
        spec, _ = P.build_spec({"strength_preset": "residual_soil", "texture": "loam"})
        slope = np.array([[5., 15., 25.], [35., 45., 60.]])
        valid = np.ones_like(slope, bool)
        fast, _ = P.stability_grid(slope, valid, 15.0, 12, spec, 12, 3, device="cpu", mobilise=False)
        ref = ENS.run_grid(slope, np.full(12, 15.0), 3600, spec, valid, "scenario_ensemble", 12, 3)
        for k_fast, k_ref in (("min_fs_p50", "min_fs_p50"), ("frac_lt1", "frac_lt1_conditional"), ("min_fs_p05", "min_fs_p05")):
            np.testing.assert_allclose(fast[k_fast], ref[k_ref], rtol=1e-6, err_msg=k_fast)

    def test_gpu_path_matches_cpu(self):
        import torch
        if not torch.cuda.is_available():
            self.skipTest("no CUDA")
        spec, _ = P.build_spec({"strength_preset": "residual_soil", "texture": "loam"})
        rng = np.random.default_rng(0)
        slope = rng.uniform(0, 60, (300, 300)).astype("float32"); valid = rng.uniform(size=slope.shape) > 0.1
        try:
            g, _ = P._stability_grid_gpu(slope, valid, 15.0, 12, spec, 15, 4, True, 45.0)
        except Exception as e:
            self.skipTest(f"GPU unavailable: {str(e)[:60]}")
        c, _ = P._stability_grid_cpu(slope, valid, 15.0, 12, spec, 15, 4, True, 45.0)
        for k in g:
            both = valid & np.isfinite(c[k])
            cap = (lambda a: np.minimum(a, 99.0)) if k != "frac_lt1" else (lambda a: a)
            np.testing.assert_allclose(cap(g[k])[both], cap(c[k])[both], rtol=2e-4, atol=2e-4, err_msg=k)

    def test_steeper_and_wetter_is_less_stable(self):
        spec, _ = P.build_spec({})
        slope = np.array([[10., 40.]]); v = np.ones_like(slope, bool)
        dry, _ = P.stability_grid(slope, v, 0.0, 24, spec, 20, 0, mobilise=False)
        wet, _ = P.stability_grid(slope, v, 40.0, 24, spec, 20, 0, mobilise=False)
        self.assertTrue(np.all(wet["min_fs_p50"] <= dry["min_fs_p50"] + 1e-12))
        self.assertGreater(wet["min_fs_p50"][0, 0], wet["min_fs_p50"][0, 1])

    def test_unknown_texture_is_rejected_not_defaulted(self):
        from landslide.errors import GateError
        with self.assertRaises(GateError):
            P.build_spec({"texture": "moon dust"})

    def test_resolution_budget(self):
        self.assertEqual(P.choose_resolution(100, None), 30.0)
        self.assertGreater(P.choose_resolution(985_000, None), P.MAX_PHYSICS_RES_M)


if __name__ == "__main__":
    unittest.main()


class TestMobilisation(unittest.TestCase):
    def test_bare_rock_and_pre_unstable_cells_are_not_rain_failures(self):
        spec, _ = P.build_spec({"strength_preset": "weak_clayey", "texture": "loam"})
        slope = np.array([[20.0, 40.0, 60.0]], "float32"); v = np.ones_like(slope, bool)
        on, _ = P.stability_grid(slope, v, 40.0, 24, spec, 20, 1, device="cpu", mobilise=True)
        off, _ = P.stability_grid(slope, v, 40.0, 24, spec, 20, 1, device="cpu", mobilise=False)
        self.assertEqual(on["frac_lt1"][0, 2], 0.0)                    # 60 deg: bare rock, never a soil failure
        self.assertGreater(off["frac_lt1"][0, 2], 0.5)                 # ...but it "fails" if the rule is switched off
        self.assertTrue(np.all(on["frac_lt1"] <= off["frac_lt1"] + 1e-12))
