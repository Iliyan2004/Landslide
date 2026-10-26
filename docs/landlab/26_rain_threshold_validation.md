# Validation 1: Rainfall Skill (completed)

## 19.1 Design

Every day-resolved, rain-triggered report from 1981 to 2026 is an event ({{rain_threshold.json:n_events|0}} events). For each, {{rain_threshold.json:controls_per_event|0}} controls were drawn at the same location on other days within 30 days of the same day of the year (any year 1981 to 2025), never within 7 days of a report within 25 km ({{rain_threshold.json:n_controls|0}} controls). Features are computed identically from ERA5-Land hourly rain: the maximum mean intensity over D hours ending within the event day (D = 1 to 168), the day total, and antecedent rain over 3, 7, 14 and 30 days before the day.

## 19.2 Single-feature skill

| Feature | AUC | 95% interval |
|---|---|---|
| Intensity 1 h | {{rain_threshold.json:feature_auc.I1.auc|3}} | {{rain_threshold.json:feature_auc.I1.ci95.0|3}} to {{rain_threshold.json:feature_auc.I1.ci95.1|3}} |
| Intensity 3 h | {{rain_threshold.json:feature_auc.I3.auc|3}} | {{rain_threshold.json:feature_auc.I3.ci95.0|3}} to {{rain_threshold.json:feature_auc.I3.ci95.1|3}} |
| Intensity 6 h | {{rain_threshold.json:feature_auc.I6.auc|3}} | {{rain_threshold.json:feature_auc.I6.ci95.0|3}} to {{rain_threshold.json:feature_auc.I6.ci95.1|3}} |
| Intensity 12 h | {{rain_threshold.json:feature_auc.I12.auc|3}} | {{rain_threshold.json:feature_auc.I12.ci95.0|3}} to {{rain_threshold.json:feature_auc.I12.ci95.1|3}} |
| Intensity 24 h | {{rain_threshold.json:feature_auc.I24.auc|3}} | {{rain_threshold.json:feature_auc.I24.ci95.0|3}} to {{rain_threshold.json:feature_auc.I24.ci95.1|3}} |
| Intensity 48 h | {{rain_threshold.json:feature_auc.I48.auc|3}} | {{rain_threshold.json:feature_auc.I48.ci95.0|3}} to {{rain_threshold.json:feature_auc.I48.ci95.1|3}} |
| Intensity 72 h | {{rain_threshold.json:feature_auc.I72.auc|3}} | {{rain_threshold.json:feature_auc.I72.ci95.0|3}} to {{rain_threshold.json:feature_auc.I72.ci95.1|3}} |
| Day total | {{rain_threshold.json:feature_auc.day_mm.auc|3}} | {{rain_threshold.json:feature_auc.day_mm.ci95.0|3}} to {{rain_threshold.json:feature_auc.day_mm.ci95.1|3}} |
| Antecedent 7 days | {{rain_threshold.json:feature_auc.A7.auc|3}} | {{rain_threshold.json:feature_auc.A7.ci95.0|3}} to {{rain_threshold.json:feature_auc.A7.ci95.1|3}} |
| Antecedent 30 days | {{rain_threshold.json:feature_auc.A30.auc|3}} | {{rain_threshold.json:feature_auc.A30.ci95.0|3}} to {{rain_threshold.json:feature_auc.A30.ci95.1|3}} |
| Antecedent precipitation index | {{rain_threshold.json:feature_auc.API.auc|3}} | {{rain_threshold.json:feature_auc.API.ci95.0|3}} to {{rain_threshold.json:feature_auc.API.ci95.1|3}} |

AUC 0.5 is no skill. Skill is flat across durations from 1 to 72 h and the antecedent measures add nothing.

## 19.3 Combined models (leave-one-year-out)

| Inputs (logistic) | AUC | 95% interval |
|---|---|---|
| 24 h intensity | {{rain_threshold.json:models.I24.auc_loyo|3}} | {{rain_threshold.json:models.I24.ci95.0|3}} to {{rain_threshold.json:models.I24.ci95.1|3}} |
| 1 h and 24 h | {{rain_threshold.json:models.I1+I24.auc_loyo|3}} | {{rain_threshold.json:models.I1+I24.ci95.0|3}} to {{rain_threshold.json:models.I1+I24.ci95.1|3}} |
| 3 h, 24 h, antecedent 7 d | {{rain_threshold.json:models.I3+I24+A7.auc_loyo|3}} | {{rain_threshold.json:models.I3+I24+A7.ci95.0|3}} to {{rain_threshold.json:models.I3+I24+A7.ci95.1|3}} |
| 24 h intensity and API | {{rain_threshold.json:models.I24+API.auc_loyo|3}} | {{rain_threshold.json:models.I24+API.ci95.0|3}} to {{rain_threshold.json:models.I24+API.ci95.1|3}} |

Adding inputs does not beat the 24 h intensity alone.

## 19.4 Thresholds

| Threshold | Share of events above | Share of control days above | TSS |
|---|---|---|---|
| Guzzetti et al. (2008), as published | {{rain_threshold.json:global_thresholds.guzzetti_2008.pod|pct}} | {{rain_threshold.json:global_thresholds.guzzetti_2008.false_alarm_rate_vs_controls|pct}} | {{rain_threshold.json:global_thresholds.guzzetti_2008.tss|2}} |
| Caine (1980), as published | {{rain_threshold.json:global_thresholds.caine_1980.pod|pct}} | {{rain_threshold.json:global_thresholds.caine_1980.false_alarm_rate_vs_controls|pct}} | {{rain_threshold.json:global_thresholds.caine_1980.tss|2}} |
| Curve fitted here, in sample | | | {{rain_threshold.json:fitted_id_threshold.tss_in_sample|2}} |
| Curve fitted here, leave-one-year-out | {{rain_threshold.json:fitted_id_threshold.pod_loyo|pct}} | {{rain_threshold.json:fitted_id_threshold.false_alarm_rate_loyo|pct}} | {{rain_threshold.json:fitted_id_threshold.tss_leave_one_year_out|2}} |

The fitted curve ({{rain_threshold.json:fitted_id_threshold.a_mm_h|3}} D^{{rain_threshold.json:fitted_id_threshold.b|3}}) is close to Guzzetti's and does **not** generalise better out of sample, so the platform keeps the published Guzzetti curve for the watch tier. Caine's curve is too high to be useful in Pakistan: it flags almost nothing.

## 19.5 Reading this result

> Rain discriminates event days from ordinary days with modest skill. The ceiling is set by the data, not by the physics: ERA5-Land at 0.1 degree smooths convective bursts, report locations are uncertain by kilometres (so the grid cell may be wrong), and only 269 of the 381 cleaned reports carry a day-resolved date (the rest cannot be used here). Satellite rainfall at sub-daily resolution (IMERG is on the server) might raise this; that has not been tested.
