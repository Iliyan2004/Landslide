# GPU Implementation and Numerical Findings

## 8.1 Backends

Compute order is GPU, then RAM, then CPU.

| Work | GPU path | Fallback |
|---|---|---|
| Runout solver | `flow_torch.FlowStateGPU`: whole-domain tensor ops, float32 with the DEM offset removed (about 1e-4 m resolution) | numba parallel kernels |
| Stability ensemble (Tier 1, national) | torch, one tensor pass per member, percentiles by sorting along the member axis | NumPy |
| Frames, rasters | host RAM (float16 frames) | n/a |

Both solver backends give the same dynamics (unit test). The page shows which backend ran.

## 8.2 Making the GPU worth using

A step is about 100 small tensor operations, so a naive GPU loop is launch-bound. Measured on the 640,000-cell grid (800 x 800):

| Variant | ms per step |
|---|---|
| numba, 20 cores | 2.66 |
| CUDA, float64, graph | 7.2 |
| CUDA, float32, graph | 1.38 |
| CUDA, float32, `torch.compile` fused kernels, graph | **0.27** |

The solver captures a CUDA graph (one launch per step; the time step is a device scalar so the graph is reused) and, for grids of 300,000 cells or more, fuses the elementwise operations with `torch.compile` (about 20 s of compilation per grid shape, cached). Small grids use the plain graph path: on a 22,000-cell area the CPU is actually faster (0.11 ms per step) than the GPU (0.3 ms), but the platform follows the owner's GPU-first rule.

## 8.3 Findings

- **Thread overhead.** With 20 numba threads a 22,000-cell grid took 8.8 ms per step against 0.11 ms with one thread; the thread count is now chosen from the grid size (one thread per 60,000 cells, at most 8).
- **Shared GPU memory.** Free GPU memory has been 1.4 to 1.9 GB of 131 GB because other users hold the rest; context creation has failed with out-of-memory. Every GPU entry point catches this and falls back to the CPU, and cached blocks are released after each job.
- **National build.** The 90 m national stability product took about 2 minutes per tile on the CPU and about 10 s per tile on the GPU (90 tiles, 49 with land).
- **Mass check.** Reported with every run: released plus entrained minus final volume was 2.8 m3 on a 1.0 million m3 flow.
