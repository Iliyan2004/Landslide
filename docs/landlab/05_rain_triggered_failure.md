# Rainfall-Triggered Failure

## 5.1 Infiltration: Green-Ampt

The wetting front depth F(t) follows Green and Ampt (1911), with infiltration equal to the smaller of rain rate and capacity:

```
f_c = Ks [ 1 + psi_f (theta_s - theta_i) / F ]
```

F does not depend on the slip depth, so it is computed once per scenario (20 sub-steps per input step). The saturated fraction of the slip layer in each cell is

```
m(t) = max( m0 , clip( F(t) / ((theta_s - theta_i) z) , 0 , 1 ) )
m0   = clip( (z - water table depth) / z , 0 , 1 )
```

This is a bounded scenario proxy for pore pressure, not groundwater head at the slip surface; rain that exceeds capacity leaves as runoff (no ponding), which is conservative for pore pressure.

## 5.2 Stability: infinite slope

```
FS = [ c' + c_r + (gamma z cos^2 b - u) tan(phi') ] / ( gamma z sin b cos b )
u  = m gamma_w z cos^2 b
```

Negative effective normal stress is clipped to zero; invalid inputs give NaN, never FS = 0; slopes under 0.5 degrees are non-failure. The saturation m at which FS = 1 is

```
m_crit = [ (c' + c_r)/(gamma z cos^2 b) + tan(phi') - tan(b) ] * gamma / ( gamma_w tan(phi') )
```

## 5.3 Failure timing

Each 15-minute step, FS is evaluated for every mobilisable cell; the first step with FS below 1 is the cell's failure time. Isolated failures smaller than 3 connected cells are dropped (pixel noise). The run records the number of failed cells against time.

## 5.4 Ensembles (Tier 1 and the national product)

For each of n members (40 by default), parameters are sampled from the ranges (Latin hypercube, Ks log-uniform) and FS is evaluated at the member's final saturation. This is exact, not an approximation: FS never increases with m, and the wetting front only advances, so the minimum over time is the value at the final m. A unit test checks it against the original time-stepped ensemble to 1e-6. The reported "share of members with FS below 1" is **conditional on the stated priors; it is not a probability.**

## 5.5 Antecedent wetness

A soil does not start every storm at the same moisture, and a front that only advances (no drainage) would otherwise treat 30 days of rain as one storm. The physics run therefore splits the rain: the storm itself drives the Green-Ampt front, and the 30 days before it set the starting state through the antecedent precipitation index

```
API = sum_i P_i k^i          daily totals before the storm, i = 1 for the day before; k = 0.90 (a ~10 day memory)
w   = clip( API / API_wet , 0 , 1 )                      API_wet = 120 mm
theta_i     = theta_r + (theta_s - theta_r) ( S_dry + (S_wet - S_dry) w )       S_dry 0.25, S_wet 0.90, theta_r 0.05
water table = water table_0 ( 1 - f_wt w )                f_wt = 0.5
```

The 30 days come from ERA5-Land (server zarr) for the same point, whichever source drives the storm (ERA5, IMERG or CHIRPS). Design storms and forecasts carry no antecedent unless the user supplies one. The constants are scenario values (`engine/antecedent.py`); `scripts/calibrate_physics.py` fits them against the event inventory with matched control days, and the fit is reported in Ch. {{ch:physics_calibration}} (a calibrated set is adopted only if it beats the defaults on held-out data). The main run and the mitigation evaluation build their scenario in one function (`run._scenario`) so that a paired run with a barrier or a planting always starts from the same soil as the unmitigated run.

## 5.6 Parameter-uncertainty ensemble

The single scenario moves every parameter together to one end of its prior range (the strength quantile). Setting `ensemble: n` in a run additionally draws n members by Latin hypercube with EVERY prior varied independently (cohesion, friction, depth, conductivity, water table, root cohesion), applies the same spatial-ground and antecedent adjustments to each member, and evaluates failure with the exact end-of-storm shortcut of Ch. {{ch:rain_triggered_failure}}.4. The outputs are a failure-probability raster (share of members in which the cell is mobilisable and fails) and the 5th, 50th and 95th percentile of the failing area. The probability is conditional on the priors and on independence between them (cohesion and friction are in fact negatively correlated in real soils); it is not a frequency of landslides. It runs on the GPU first.

## 5.7 Limits

Uniform rain over the area; no lateral flow or perched water table; no unsaturated suction strength; one soil layer; depth of failure is the soil depth, not a mapped slip surface; no rock slopes (Ch. {{ch:limitations}}).
