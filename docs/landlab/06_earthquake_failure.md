# Earthquake-Triggered Failure

## 6.1 Ground motion

The user gives a magnitude, a focal depth, an epicentre and a time. If a mapped fault lies within 25 km, the epicentre snaps to it and a rupture segment is centred on that point along the trace; otherwise the rupture is a point. The rupture length follows Wells and Coppersmith (1994): `log10 L = -2.44 + 0.59 M`. Two ground-motion models are used, chosen by depth (`SLAB_DEPTH_KM` = 40 km):

| Event | Model | Distance used | Site term |
|---|---|---|---|
| Shallow crustal, depth up to 40 km | Boore, Stewart, Seyhan and Atkinson (2014), NGA-West2, PGA, median RotD50 | Rjb: distance from each cell to the surface projection of the rupture line | Vs30 (linear and non-linear terms) |
| Intermediate depth, deeper than 40 km (Hindu Kush, Pamir) | Abrahamson et al. (2016) BC Hydro intraslab, PGA, with a regional adjustment of `SLAB_REGIONAL_LN` = -0.65 ln units | Hypocentral distance `sqrt(d_epi^2 + depth^2)` (point source) | Vs30 |

The 1981 Joyner and Boore relation is kept as `gmpe: "jb81"` for comparison only (it saturates poorly: it gives 0.56 g at 10 km for M 7.6 on rock, where NGA-West2 gives about 0.28 g).

**Site amplification.** Vs30 comes from the USGS global grid (Heath et al. 2020, 30 arc seconds; `datasets/external/vs30/vs30_pk.tif`), with a slope-based fallback (Wald and Allen 2007) where the grid has no value. Valley fill amplifies (a soil site of Vs30 300 m/s shakes about 1.4 to 1.7 times a rock site at moderate distance), so the same earthquake now shakes a river terrace harder than the ridge above it. The model name and Vs30 source are written into every quake run's summary.

## 6.2 Validation against USGS ShakeMaps

The archive holds {{pga_validation.json:events|0}} ShakeMaps (M 5.5 and above since 1973, in and around Pakistan, {{pga_validation.json:cells|0}} grid cells), of which {{pga_validation.json:events_deep_gt40km|0}} are intermediate-depth events. The comparison is with the USGS product, which is itself a model (a ground-motion equation, adjusted to station data where there are stations and to site amplification), so it tests agreement with the standard product, not with ground truth. Errors are `ln(model) - ln(ShakeMap)`.

| Events | Model | Bias (ln units) | Scatter (ln units) |
|---|---|---|---|
| Shallow, up to 40 km | Joyner and Boore 1981 | {{pga_validation.json:pooled.jb81.shallow_le40km.bias_ln|2}} | {{pga_validation.json:pooled.jb81.shallow_le40km.sd_ln|2}} |
| Shallow, up to 40 km | NGA-West2 (platform default) | {{pga_validation.json:pooled.bssa14.shallow_le40km.bias_ln|2}} | {{pga_validation.json:pooled.bssa14.shallow_le40km.sd_ln|2}} |
| Deeper than 40 km | Joyner and Boore 1981 | {{pga_validation.json:pooled.jb81.deep_gt40km.bias_ln|2}} | {{pga_validation.json:pooled.jb81.deep_gt40km.sd_ln|2}} |
| Deeper than 40 km | NGA-West2 (wrong physics for a slab event) | {{pga_validation.json:pooled.bssa14.deep_gt40km.bias_ln|2}} | {{pga_validation.json:pooled.bssa14.deep_gt40km.sd_ln|2}} |
| Deeper than 40 km | BC Hydro intraslab with the regional adjustment (platform default) | {{pga_validation.json:pooled.auto.deep_gt40km.bias_ln|2}} | {{pga_validation.json:pooled.auto.deep_gt40km.sd_ln|2}} |
| All events | platform default model (`auto`) | {{pga_validation.json:pooled.auto.all.bias_ln|2}} | {{pga_validation.json:pooled.auto.all.sd_ln|2}} |

What this shows, plainly:

- For shallow events the two relations agree with ShakeMap about equally in aggregate (scatter about 0.43 ln units, a factor of 1.5). The NGA-West2 model is kept because it is the standard, has correct magnitude scaling and carries the site term. For M 7 and above both under-predict ShakeMap (see below).
- The global BC Hydro intraslab model over-predicts the Hindu Kush ShakeMaps by 0.65 ln units (a factor of 1.9) almost independently of distance, so a single regional factor is fitted. After removing it the scatter is {{pga_validation.json:pooled.auto.deep_gt40km.sd_ln|2}}. The factor is fitted to the ShakeMap product on all {{pga_validation.json:events_deep_gt40km|0}} events (in sample); the three magnitude and depth classes give 0.33 to 0.73, so it is not constant, only typical.
- Near-field cells (under 15 km) are over-predicted by both shallow models (about +0.5 ln units) because the rupture here is a centred line of the Wells and Coppersmith length with an unknown orientation and the distance is the distance to that line; real ShakeMaps use the mapped finite fault and, near it, station data. Large events (M 7 and above) are under-predicted by about 0.4 ln units for the same reason: a long fault puts more of the area close to the rupture than a centred line assumes. Where the finite fault is known, its trace should replace the centred line.

**Does a mapped fault trace help?** The platform already snaps the epicentre to a mapped fault within 25 km and centres the rupture segment on it (the validation script now does the same, `rupture_distance`). Comparing that with the plain centred-point distance on the {{pga_validation.json:fault_trace.cells_with_fault|0}} shallow-event cells that have a mapped fault within 25 km:

| Cells | Distance used | Bias (ln) | Scatter (ln) |
|---|---|---|---|
| Near field, under 15 km | centred point | {{pga_validation.json:fault_trace.near_field_lt15km_with_fault.centred_line.bias_ln|2}} | {{pga_validation.json:fault_trace.near_field_lt15km_with_fault.centred_line.sd_ln|2}} |
| Near field, under 15 km | fault trace | {{pga_validation.json:fault_trace.near_field_lt15km_with_fault.fault_trace.bias_ln|2}} | {{pga_validation.json:fault_trace.near_field_lt15km_with_fault.fault_trace.sd_ln|2}} |
| M 6.5 and above | centred point | {{pga_validation.json:fault_trace.M65_plus_with_fault.centred_line.bias_ln|2}} | {{pga_validation.json:fault_trace.M65_plus_with_fault.centred_line.sd_ln|2}} |
| M 6.5 and above | fault trace | {{pga_validation.json:fault_trace.M65_plus_with_fault.fault_trace.bias_ln|2}} | {{pga_validation.json:fault_trace.M65_plus_with_fault.fault_trace.sd_ln|2}} |

The fault trace removes most of the near-field over-prediction (+0.57 to +0.17) but widens the scatter, and for M 6.5 and above it makes the under-prediction worse (-0.05 to -0.24). So the large-event under-prediction is not a fault-geometry problem: the Wells and Coppersmith length is the subsurface rupture length, while ShakeMap uses the finite fault of each event, and the equation's own saturation also matters. Nothing was tuned to this: the model keeps snapping to a mapped fault, and the large-event bias (about a quarter lower than ShakeMap) is stated as a known limit.

> **Reading the numbers.** A scatter of 0.43 ln units means the model is within a factor of 1.5 of ShakeMap about two times in three. Newmark displacement is very sensitive to PGA (roughly the fourth power near the yield acceleration), so an error of this size is the largest uncertainty in the earthquake chapters (Ch. {{ch:tier4_earthquake}}).

## 6.3 Newmark displacement

The yield coefficient of a dry slope (Ch. {{ch:rain_triggered_failure}} formula with m = 0) is converted to displacement by the Jibson (2007) regression

```
log10 Dn(cm) = 0.215 + log10 [ (1 - ky/PGA)^2.341 (ky/PGA)^-1.438 ]       (sigma = 0.51 log units)
```

A cell fails if Dn is at least a critical displacement (5 cm by default; user-set). The same mobilisation rule applies (Ch. {{ch:terrain_parameters}}.5), so slopes already unstable when dry are excluded, not counted as quake failures. An optional preceding rain series can be combined with the quake (mode "both"). Released masses start moving at the quake time.

> A magnitude 6.8 earthquake on top of the Gilgit test area now gives a different picture from the 1981 relation, because the shaking depends on site conditions. The criterion matters as much as the shaking: with the 5 cm default few cells fail, while a 2 cm criterion at M 7.2 fails several square kilometres. The Gilgit example numbers are in Ch. {{ch:tier4_earthquake}}.
