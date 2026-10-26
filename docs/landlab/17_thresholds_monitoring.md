# Intensity-Duration Thresholds and Live Monitoring

## 15.1 Global thresholds

For the watch tier the platform uses published global curves, not a Pakistan-specific fit (Ch. {{ch:rain_threshold_validation}} shows a fit does no better on the available data):

```
Caine (1980):             I = 14.82 D^-0.39    (mm/h, D in hours, 0.167 to 500 h)
Guzzetti et al. (2008):   I = 2.20  D^-0.44    (mm/h, D in hours, 0.1 to 1000 h)
```

For a rain series the maximum mean intensity over 1, 3, 6, 12, 24, 48 and 72 h is compared with the curve; exceedance at any duration is reported. The status is always `experimental_unvalidated`, and the page says a threshold exceedance is a watch, never a prediction. An antecedent precipitation index (k = 0.98 per hour on the last three days) is shown beside it.

## 15.2 Live monitoring

A watch stores an area, a forecast-intensity threshold (default 10 mm/h), a check interval and an optional webhook. A scheduler thread wakes every 60 s and checks the watches that are due: it fetches the Open-Meteo forecast for the area centre, and when the forecast peak crosses the threshold (and the previous check had not) it starts a Tier 3 run on that forecast and posts to the webhook. Watches are stored in `datasets/state/watches.json`.

> Monitoring uses a point forecast and uniform rain, and the Tier 3 physics is screening grade; an automatic run is an early look, not a warning.
