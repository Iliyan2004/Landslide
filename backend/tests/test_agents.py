import tempfile, unittest
from pathlib import Path
from unittest import mock
import numpy as np
from landslide.app import agents as AG, rainfall as RF
from landslide.errors import GateError


class TestAgents(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.p = [mock.patch.object(AG, "EVENTS", self.tmp / "e.jsonl"), mock.patch.object(AG, "FORECASTS", self.tmp / "f.jsonl"),
                                                       mock.patch.object(AG, "BIAS", self.tmp / "b.json")]
        [p.start() for p in self.p]; AG._sources.clear(); AG._cache.clear()

    def tearDown(self):
        [p.stop() for p in self.p]

    def test_classify(self):
        self.assertEqual(AG.classify(GateError(["x"])), "user_input")
        self.assertEqual(AG.classify(RuntimeError("CUDA out of memory")), "gpu")
        self.assertEqual(AG.classify(TimeoutError("timed out")), "network")
        self.assertEqual(AG.classify(ValueError("bad")), "other")

    def test_gpu_failure_is_retried_on_cpu_and_recorded(self):
        calls = []
        def fn(p):
            calls.append(p.get("backend"))
            if p.get("backend") != "numba":
                raise RuntimeError("CUDA error: out of memory")
            return {"run_id": "x", "warnings": []}
        r = AG.run_with_recovery(fn, {"mode": "rain"})
        self.assertEqual(calls, [None, "numba"]); self.assertIn("CPU", r["recovery"]["action"]); self.assertTrue(any("Recovered" in w for w in r["warnings"]))
        self.assertTrue(any(e["kind"] == "job_recovered" for e in AG.recent_events()))

    def test_user_and_unknown_errors_are_not_retried(self):
        n = [0]
        def bad(p):
            n[0] += 1; raise GateError(["too big"])
        with self.assertRaises(GateError):
            AG.run_with_recovery(bad, {})
        self.assertEqual(n[0], 1)

    def test_open_meteo_falls_back_to_a_fresh_cache_then_fails(self):
        good = {"source": "Open-Meteo", "rate_mm_h": [1.0] * 5, "now_hour_index": 2}
        with mock.patch.object(RF, "_open_meteo_raw", return_value=good), mock.patch("time.sleep"):
            self.assertEqual(RF.open_meteo(35.9, 74.3)["rate_mm_h"], good["rate_mm_h"])
        with mock.patch.object(RF, "_open_meteo_raw", side_effect=ConnectionError("down")), mock.patch("time.sleep"):
            r = RF.open_meteo(35.9, 74.3); self.assertTrue(r["stale_cache"]); self.assertIn("CACHED", r["source"])
            self.assertEqual(AG._sources["open-meteo"]["consecutive_fail"], 1)
            with self.assertRaises(ConnectionError):
                RF.open_meteo(10.0, 10.0)                                               # nothing cached for that point
        with mock.patch.object(RF, "_open_meteo_raw", return_value=good), mock.patch("time.sleep"):
            RF.open_meteo(35.9, 74.3)
        self.assertEqual(AG._sources["open-meteo"]["consecutive_fail"], 0); self.assertTrue(any(e["kind"] == "source_recovered" for e in AG.recent_events()))

    def test_forecast_scores_and_bias_factor(self):
        f = np.r_[np.full(24, 1.0), np.full(24, 0.0)]; o = np.r_[np.full(24, 0.5), np.full(24, 2.0)]
        s = AG.score_pair(f, o, thr_mm_day=40.0); self.assertEqual([x["lead_day"] for x in s], [0, 1]); self.assertAlmostEqual(s[0]["fcst_mm"], 24.0)
        rows = [{"lead_day": 1, "fcst_mm": 10.0, "obs_mm": 5.0}] * 200
        fac = AG.bias_from_scores(rows, prior_n=10.0)["1"]; self.assertAlmostEqual(fac["raw_ratio"], 0.5); self.assertTrue(0.5 <= fac["factor"] < 0.6)
        self.assertEqual(AG.bias_from_scores([{"lead_day": 0, "fcst_mm": 1.0, "obs_mm": 100.0}], 10.0)["0"]["factor"] < 2.0, True)   # one wet day cannot swing the factor
        self.assertEqual(AG.correction(0), 1.0)                                                                                          # nothing audited: no correction

    def test_health_snapshot_has_the_parts(self):
        h = AG.health(); self.assertIn(h["status"], ("ok", "degraded", "down")); self.assertIn("gpu", h); self.assertIn("era5", h)


if __name__ == "__main__":
    unittest.main()
