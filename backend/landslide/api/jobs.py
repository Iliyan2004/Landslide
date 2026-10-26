"""Idempotent, cancellable job store (thread-pool). Swap for Celery/RQ in production via the same interface."""
from __future__ import annotations
import threading, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from ..errors import GateError, InsufficientData, LandslideError

STATES = ("queued", "running", "succeeded", "failed", "insufficient_data", "gate_rejected", "cancelled")


class JobStore:
    def __init__(self, workers=2):
        self.pool = ThreadPoolExecutor(workers)
        self.jobs, self.by_key, self.lock = {}, {}, threading.Lock()

    def submit(self, kind, cache_key, fn, *args, **kw):
        with self.lock:                                        # idempotent: same cache key => same job
            if cache_key in self.by_key and self.jobs[self.by_key[cache_key]]["state"] in ("queued", "running", "succeeded"):
                return self.by_key[cache_key]
            jid = str(uuid.uuid4())
            self.jobs[jid] = {"id": jid, "kind": kind, "state": "queued", "stage": "queued", "progress": 0.0,
                              "cancel": False, "result": None, "error": None, "cache_key": cache_key}
            self.by_key[cache_key] = jid
        self.pool.submit(self._run, jid, fn, args, kw)
        return jid

    def _run(self, jid, fn, args, kw):
        j = self.jobs[jid]
        if j["cancel"]:
            j["state"] = "cancelled"; return
        j["state"] = "running"
        def progress(stage, frac):
            if j["cancel"]:
                raise InterruptedError("cancelled")
            j["stage"], j["progress"] = stage, frac
        try:
            j["result"] = fn(*args, progress=progress, **kw)
            j["state"], j["progress"] = "succeeded", 1.0
        except InterruptedError:
            j["state"] = "cancelled"
        except InsufficientData as e:
            j["state"], j["error"] = "insufficient_data", {"code": e.code, "missing": e.missing, "message": str(e)}
        except GateError as e:
            j["state"], j["error"] = "gate_rejected", {"code": e.code, "reasons": e.reasons}
        except LandslideError as e:
            j["state"], j["error"] = "failed", {"code": e.code, "message": str(e)}
        except Exception as e:                                   # noqa: BLE001
            j["state"], j["error"] = "failed", {"code": "internal", "message": str(e), "trace": traceback.format_exc(limit=3)}

    def get(self, jid):
        return self.jobs.get(jid)

    def cancel(self, jid):
        if jid in self.jobs:
            self.jobs[jid]["cancel"] = True
            if self.jobs[jid]["state"] == "queued":
                self.jobs[jid]["state"] = "cancelled"
        return self.jobs.get(jid)
