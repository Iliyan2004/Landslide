"""Explicit failure states. Methodology §1.3 / §4.7: never silently substitute data."""


class LandslideError(Exception):
    code = "error"


class InsufficientData(LandslideError):
    """Essential variable missing for the requested fidelity (returns `insufficient_data`)."""
    code = "insufficient_data"

    def __init__(self, missing, model=""):
        self.missing = list(missing)
        self.model = model
        super().__init__(f"{model or 'model'} cannot run: missing {', '.join(self.missing)}")


class GateError(LandslideError):
    """An acceptance gate (§4.7) rejected the run."""
    code = "gate_rejected"

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


class SourceUnavailable(LandslideError):
    """A fetch was blocked/failed. Never fabricate data (§11.2)."""
    code = "source_unavailable"
