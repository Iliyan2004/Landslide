"""Rockfall engine checks on synthetic terrain (CPU, tiny): free fall, stopping on flat ground, energy sanity, barriers, determinism."""
import unittest
import numpy as np
from landslide.engine import rockfall as RK


def _slope(n=120, dx=10.0, tan=0.9, flat_from=80):
    r = np.arange(n)[:, None] * np.ones((1, n))
    Z = np.where(r < flat_from, (flat_from - r) * dx * tan, 0.0)
    return Z.astype("float32"), dx


class TestRockfall(unittest.TestCase):
    def test_rocks_start_on_the_cliff_run_down_and_stop_on_the_flat(self):
        Z, dx = _slope()
        res = RK.simulate(Z, dx, ([10] * 3, [40, 60, 80]), rocks_per_source=15, d50=0.8, rough_deg=8, t_max=60, device="cpu", seed=1, track=10)
        self.assertEqual(res["n_rocks"], 45)
        self.assertGreater(int((res["state"] == 2).sum()), 30)                     # most rocks come to rest
        stop_rows = res["stop_xy"][:, 1] / dx
        self.assertTrue(np.mean(stop_rows > 60) > 0.6)                             # they ran out onto the lower slope / flat
        self.assertGreater(res["emax_j"].max(), 5e4)                               # tens of kJ after a ~700 m drop is plausible (>50 kJ)
        self.assertTrue(np.isfinite(res["travel_angle_deg"]).all())
        self.assertLess(np.median(res["travel_angle_deg"]), 45)                    # reach angle is below the slope angle (they travel on)

    def test_energy_cannot_exceed_the_potential_energy_released(self):
        Z, dx = _slope()
        res = RK.simulate(Z, dx, ([5], [60]), rocks_per_source=20, d50=0.6, t_max=60, device="cpu", seed=2, track=5)
        mass_max = 4 / 3 * np.pi * (res["diameter_m"].max() / 2) ** 3 * RK.RHO
        drop = float(Z[5, 60] - Z.min()) + 1.0
        self.assertLess(res["emax_j"].max(), mass_max * RK.G * drop * 1.05)        # translational KE <= m g (drop): energy is dissipated, never created

    def test_softer_surface_shortens_the_runout(self):
        Z, dx = _slope()
        n = Z.shape
        hard = RK.surface_maps(np.full(n, 7.0), n, "rock"); soft = RK.surface_maps(np.full(n, 2.0), n, "talus")
        a = RK.simulate(Z, dx, ([8] * 4, [30, 50, 70, 90]), rocks_per_source=20, rn=hard[0], rt=hard[1], mu=hard[2], t_max=90, device="cpu", seed=3, track=4)
        b = RK.simulate(Z, dx, ([8] * 4, [30, 50, 70, 90]), rocks_per_source=20, rn=soft[0], rt=soft[1], mu=soft[2], t_max=90, device="cpu", seed=3, track=4)
        self.assertGreater(np.mean(a["stop_xy"][:, 1]), np.mean(b["stop_xy"][:, 1]))   # forest/soft surface stops them sooner (smaller row)

    def test_barrier_stops_rocks_with_energy_below_capacity(self):
        Z, dx = _slope()
        cap = np.zeros(Z.shape, "float32"); ht = np.zeros(Z.shape, "float32"); bid = np.zeros(Z.shape, "int64")
        cap[55:57, :] = 1e6; ht[55:57, :] = 50.0                                   # a very strong, very high fence across the whole slope
        free = RK.simulate(Z, dx, ([8] * 3, [40, 60, 80]), rocks_per_source=15, t_max=60, device="cpu", seed=4, track=3)
        prot = RK.simulate(Z, dx, ([8] * 3, [40, 60, 80]), rocks_per_source=15, t_max=60, device="cpu", seed=4, track=3, barriers={"cap_kj": cap, "height": ht, "id": bid})
        self.assertGreater(free["reach_count"][70:, :].sum(), 0)
        self.assertEqual(prot["reach_count"][70:, :].sum(), 0)                      # nothing gets past the fence
        self.assertGreater(prot["stops"][54:58, :].sum(), 0)                        # they are stopped AT the fence

    def test_same_seed_same_result(self):
        Z, dx = _slope(60)
        a = RK.simulate(Z, dx, ([5], [30]), rocks_per_source=10, t_max=40, device="cpu", seed=9, track=3)
        b = RK.simulate(Z, dx, ([5], [30]), rocks_per_source=10, t_max=40, device="cpu", seed=9, track=3)
        np.testing.assert_allclose(a["stop_xy"], b["stop_xy"])


if __name__ == "__main__":
    unittest.main()
