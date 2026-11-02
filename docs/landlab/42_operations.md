# Operations and Testing

## 30.1 Running

```
~/flood/venv/bin/python landslide_app.py                    # http://<host>:5070 (Flask, token in .env)
nice ~/flood/venv/bin/python scripts/build_national.py      # national 90 m product, GPU first, resumable
~/flood/venv/bin/python scripts/build_districts.py          # after the national build prints DONE
~/flood/venv/bin/python scripts/build_landlab_techref.py    # rebuilds this document from docs/landlab and docs/validation
```

Compute-heavy validation and calibration scripts are run only on request: `validate_rain_threshold.py` (done), `validate_spatial.py` (written), later `calibrate_physics.py` and the runout and PGA checks. `scripts/calibrate_physics.py`, `check_runout_relations.py` and `validate_pga.py` are written and not run. Also compute heavy and run only on request: the CMIP6 climate multiplier, average annual loss, automatic barrier placement and mitigated-versus-unmitigated pairs (each is one or more full simulations).

## 30.2 Tests

`cd backend && PYTHONPATH=. ~/flood/venv/bin/python -m unittest discover -s tests -t .` runs {{TESTS}} tests: the original physics and integrity tests, the app layer (fast ensemble equals the reference, GPU equals CPU, mobilisation rule), and the engine (mass, rest, speed, entrainment, GPU equals CPU, Joyner-Boore, Wells-Coppersmith, mobilisation). GPU tests skip if the shared GPU cannot be initialised.

## 30.3 Files

| Path | Content |
|---|---|
| `runs/<id>/` | one run: summary, manifest, arrays, frames, 3D scene |
| `datasets/national/` | national product, district statistics, build log |
| `datasets/derived/` | 30 m slope raster for validation |
| `datasets/state/` | monitoring watches, run history |
| `docs/validation/` | JSON results and sample tables that this document reads |

## 30.4 Safety

One heavy job at a time; the GPU is shared, so it is released after every job; any GPU failure falls back to the CPU; all data paths are read-only; the application never writes into SAILAB or the shared data folders.
