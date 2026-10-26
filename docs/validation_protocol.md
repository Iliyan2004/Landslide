# Validation protocol (methodology §6.1, §9)

No model output may be labelled beyond its validation status. `manifest.validation_status` ∈
`screening_only → spatially_validated → event_validated → operationally_validated`.

## Observation hierarchy (§9.1)
1 Event-dated scar polygons, GNSS/borehole/piezometer, calibrated gauges, measured deposits ·
2 Cloud-screened hi-res optical, ShakeMaps, coherent InSAR · 3 Reference only: published inventories, global land products, LHASA, reanalysis ·
4 Scenarios, NOT observations: friction-angle lookups, inferred soil depth, assumed groundwater, assumed runout friction.

## Per-component tests
| Component | Split | Metrics | Release guard |
|---|---|---|---|
| Susceptibility (M02-M04) | Geographic blocks (`spatial_blocks`) + whole-event holdout (`event_holdout`) + one independent region | PR-AUC (vs prevalence), ROC-AUC, Brier, reliability (`reliability`) | No national-skill claim from random-pixel CV; OOD cells suppressed |
| Rainfall threshold (M07) | Independent event AND non-event dates | POD, FAR, CSI (`contingency`), lead time | Calibrated probability only with documented detection coverage |
| Infiltration/pore pressure | Measured moisture / water table / suction | MAE, bias, NSE, mass-balance residual | Flag parameter + BC uncertainty |
| Infinite slope FS | Known stable/unstable sites | ROC/PR, FS distribution, sensitivity | No site certification without ground investigation |
| Newmark | Documented sliding extents | Bias, spatial detection | Never "measured deformation" |
| Runout | Independently mapped reach/deposit | CSI/IoU, length error, depth RMSE, volume balance | Never tune and validate on the same event |
| Sediment | Observed SSC/bedload | Bias, NSE/KGE, budget closure | Capacity-only wording where unobserved |
| Exposure | Sample building/road checks | Completeness, false intersects | Unmapped assets ≠ zero risk |

## Procedure
1. Freeze inventory snapshot (hash). Split by **block/basin/event BEFORE** any preprocessing, tuning or feature selection.
2. Fit imputers/scalers inside training folds only (pipelines in `statistical.py` do this).
3. Never fit ML to M01 or LHASA outputs and claim independent skill.
4. Record metrics in `quality_report.json` and update `calibration_status`/`validation_status` in the manifest.
5. Reserve a geographically separate basin + whole events for untouched final validation (§10 pilot).

## Gate before live alerting (§9.4)
Held-out regional event set; retrospective seasonal hindcast; false-alarm audit; calibrated class thresholds;
documented human escalation path; fallback when weather/satellite feeds fail; real communications and agency procedures.
Until all are met `watch_state()` returns `status: experimental_unvalidated`.
