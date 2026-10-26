"""Shared-server heat governor. The DGX has hard-reset under sustained load (see project notes), so every heavy loop
calls Governor.wait(): it pauses while the hottest sysfs thermal zone is at/above BACKOFF and resumes below RESUME.
Limits come from the user's agreed values (back off 91 C, resume 87 C); override with LANDSLIDE_TEMP_BACKOFF / _RESUME."""
from __future__ import annotations
import glob, os, time

BACKOFF = float(os.environ.get("LANDSLIDE_TEMP_BACKOFF", 91.0))
RESUME = float(os.environ.get("LANDSLIDE_TEMP_RESUME", 87.0))
# User decision 2026-10-23: no temperature guard. Opt back in with LANDSLIDE_TEMP_GUARD=1.
ENABLED = os.environ.get("LANDSLIDE_TEMP_GUARD", "0") == "1"
MAX_WAIT_S = float(os.environ.get("LANDSLIDE_TEMP_MAX_WAIT", 1800))


def hottest_c():
    best = 0.0
    for f in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            best = max(best, int(open(f).read().strip()) / 1000.0)
        except (OSError, ValueError):
            pass
    return best


class Governor:
    def __init__(self, on_wait=None):
        self.paused_s = 0.0
        self.last = 0.0
        self.on_wait = on_wait
        self.peak_c = 0.0

    def wait(self):
        if not ENABLED:
            return
        now = time.time()
        if now - self.last < 1.0:
            return
        self.last = now
        t = hottest_c(); self.peak_c = max(self.peak_c, t)
        if t < BACKOFF:
            return
        t0 = time.time()
        while hottest_c() > RESUME:
            if self.on_wait:
                self.on_wait(hottest_c())
            time.sleep(2.0)
            if time.time() - t0 > MAX_WAIT_S:
                raise RuntimeError(f"server stayed above {RESUME:.0f} C for {MAX_WAIT_S:.0f} s; run aborted to protect it")
        self.paused_s += time.time() - t0
        self.last = time.time()
