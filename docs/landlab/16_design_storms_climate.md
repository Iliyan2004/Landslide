# Design Storms and Climate Scaling

## Source data

A per-cell rainfall-indices cube already on the server (built by another task, read-only): ERA5-Land hourly precipitation 1980 to 2025 (0.1 degree) reduced to the annual maximum accumulation over running windows of 1, 2, 3, 6, 12 and 24 h, and a GPM IMERG V07 30-minute product (2000 to 2026) giving annual maxima of intensity over 30, 60, 90, 120 and 180 minutes. The IMERG variable is an **intensity in mm per hour** (checked in the file's attributes); the depth for a duration is intensity times duration. Using it as a depth would have inflated sub-hourly storms (found when the 1 h hyetograph summed to 9.1 mm instead of 8.0 mm).

## Return-period depths

For each duration, a Gumbel (EV1) distribution is fitted by L-moments to the 46 annual maxima, which is stable at that sample size where a three-parameter GEV is not:

```
alpha = l2 / ln 2,   xi = l1 - 0.5772 alpha
depth(T, D) = xi - alpha ln( -ln(1 - 1/T) ),    T = 2, 5, 10, 25, 50, 100, 200 years
```

Depth is forced non-decreasing in duration. A 90% interval comes from 100 parametric-bootstrap refits. A synthetic test recovers known parameters (xi 39.8 against 40, alpha 12.0 against 12). The record is 46 years, so 100- and 200-year values are extrapolations and the interval says so.

## The hyetograph

An alternating-block hyetograph: the incremental depths of the cumulative curve P(D) are sorted and the largest block is placed at the middle, the next either side, and so on. P(D) is interpolated log-log between the fitted durations. Below one hour the shape comes from the IMERG ratio of depth at D to depth at 60 minutes (median over years) and the level from ERA5; without IMERG the 1 to 3 h power law is extended. The total depth equals the fitted IDF depth exactly (tested at 3, 6 and 24 h; checked at Gilgit: 17.85, 28.03 and 65.93 mm for T = 100). Storms are limited to 24 h, the longest window of the record. **Point rainfall is used: no areal reduction factor is applied**, which is conservative for the areas this platform runs.

> At Gilgit the observed 100-year, 24 h depth is only 66 mm, whereas the reference test storm of Ch. {{ch:tier3_pipeline}} (360 mm) is five times that. It is an extreme stress test, not a design storm. Elsewhere, such as the Kashmir monsoon belt, the 24 h depths are several times larger. ERA5-Land smooths cloudbursts, so every depth here is a lower bound for short durations.

## Climate scaling

The delta-change method with the NASA NEX-GDDP-CMIP6 daily precipitation archive on the server: for up to eight models, the Gumbel T-year daily value is fitted to 1985 to 2014 (historical) and to the chosen future window (2036 to 2065 or 2071 to 2100, SSP2-4.5 or SSP5-8.5); the ratio of the two is taken per model and the **median ratio** is used as a multiplier on the design storm. Taking the ratio cancels each model's own bias against observation. Reading the yearly files (about 30 MB each, up to 480 files) takes minutes, so it runs only when asked and is cached by location, scenario, period and return period. Only daily data exist, so the multiplier is applied uniformly to all durations; sub-daily intensification is probably stronger than daily and is not represented. **Not yet run on real data.**
