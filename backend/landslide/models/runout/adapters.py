"""External multiphase engines (M16 r.avaflow, M09 Richards, M10 TRIGRS) are NOT reimplemented here.

Methodology §5.3/§6: use verified solvers via isolated-container CLI adapters. These adapters define the contract and
fail loudly (`InsufficientData`/`NotImplementedError`) until a validated engine image is configured.
"""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from ...errors import InsufficientData
from ...gates import check_runout_source


class ExternalEngine:
    name = "external"
    required = ()
    image_env = "ENGINE_IMAGE"

    def __init__(self, config: dict):
        self.config = config

    def validate(self, inputs: dict):
        missing = [k for k in self.required if inputs.get(k) is None]
        if missing:
            raise InsufficientData(missing, self.name)

    def write_job(self, workdir, inputs):
        w = Path(workdir)
        w.mkdir(parents=True, exist_ok=True)
        (w / "job.json").write_text(json.dumps(inputs, indent=2, default=str))
        return w / "job.json"

    def run(self, workdir, inputs):
        self.validate(inputs)
        image = self.config.get("image")
        if not image:
            raise NotImplementedError(f"{self.name}: no validated engine image configured (set engines.{self.name}.image)")
        if shutil.which("docker") is None:
            raise NotImplementedError("docker not available for isolated engine execution")
        job = self.write_job(workdir, inputs)
        cmd = ["docker", "run", "--rm", "--network=none", "--memory", self.config.get("memory", "8g"),
               "-v", f"{Path(workdir).resolve()}:/work", image, "/work/job.json"]
        subprocess.run(cmd, check=True, timeout=self.config.get("timeout_s", 3600))
        return json.loads((Path(workdir) / "result.json").read_text())


class RAvaflow(ExternalEngine):
    name = "r.avaflow"
    required = ("dem", "release_polygon", "release_height_m", "rheology", "phase_fractions")

    def validate(self, inputs):
        super().validate(inputs)
        check_runout_source(inputs["release_polygon"], inputs.get("release_volume_m3", 1))


class RichardsSolver(ExternalEngine):
    name = "richards_1d"
    required = ("van_genuchten", "layers", "initial_condition", "boundary_conditions", "rain_series")


class TRIGRS(ExternalEngine):
    name = "trigrs"
    required = ("slope", "soil_depth", "Ksat", "diffusivity", "rain_series", "initial_water_table")
