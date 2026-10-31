# Accuracy Record

| Claim | Evidence | Status |
|---|---|---|
| The code solves its equations | {{TESTS}} unit tests; mass conservation, rest, Voellmy speed, entrainment, GPU equals CPU, fast ensemble equals the reference ensemble | **Verified** |
| Rainfall separates landslide days from ordinary days | AUC {{rain_threshold.json:feature_auc.I24.auc|2}} ({{rain_threshold.json:feature_auc.I24.ci95.0|2}} to {{rain_threshold.json:feature_auc.I24.ci95.1|2}}) for 24 h intensity, leave-one-year-out | **Validated, modest** |
| Published Guzzetti threshold is usable as a watch | TSS {{rain_threshold.json:global_thresholds.guzzetti_2008.tss|2}} on the same data | **Validated, weak** |
| Slopes flagged by the physics are the slopes that fail | Ground calibration, held-out blocks: base physics {{ground_calibration.json:variants.base.auc_heldout|2}}, with soil texture {{ground_calibration.json:variants.+texture.auc_heldout|2}}; mean slope {{ground_calibration.json:slope_mean_auc_no_fit.auc|2}} | **Weak** |
| Calibrated parameters are better than the defaults | Held-out AUC {{physics_calibration.json:default.auc|2}} to {{physics_calibration.json:calibrated.auc|2}} (144 events) | **Improved, wide interval** |
| Runout lengths are realistic | Corominas relations on synthetic slopes (Ch. {{ch:runout_calibration}}) | **Right order of magnitude, within a factor of about 2** |
| Earthquake PGA is realistic | {{pga_validation.json:events|0}} ShakeMaps: scatter {{pga_validation.json:pooled.auto.all.sd_ln|2}} ln units (Ch. {{ch:earthquake_failure}}.2) | **Agrees with ShakeMap, which is itself a model** |
| Shaking locates earthquake-triggered landslide reports | {{quake_landslides.json:n_events|0}} reports, {{quake_landslides.json:earthquakes|0}} earthquakes: PGA AUC {{quake_landslides.json:auc.pga_mean.auc|2}}, Newmark {{quake_landslides.json:auc.newmark_bssa_p90.auc|2}}, slope {{quake_landslides.json:auc.slope_p90.auc|2}} | **Not shown (n too small, reports cluster at roads)** |
| Observed design storms are right | Gumbel fits recover known parameters; hyetograph depth equals the IDF depth; ERA5-Land smooths bursts | **Verified arithmetic; depths are lower bounds** |
| Mitigation levers and barriers behave sensibly | Directional and mass tests on synthetic cases | **Verified; effect sizes are user inputs, not validated** |
| Dam screening classes and formulas | Formula and synthetic-valley tests; no observed Pakistani dam used | **Verified; not validated** |
| Annual average loss is realistic | Integration verified; assumes loss frequency equals rainfall frequency | **Verified arithmetic; not validated** |
| Rockfall reach and energy are realistic | Synthetic-terrain physics checks pass; first Hunza run has reach angles above literature shadow angles | **Verified code; not validated; probably too dissipative** |
| Access and isolation analysis is right | Synthetic network tests; no observed closures | **Verified logic; not validated** |
| Building damage and loss are realistic | No data | **Not validated, assumed** |
| Flow depth and deposit extent are right | No mapped deposits | **Not validated** |

## 23.1 What the accuracy depends on

The largest controllable limits are data: report locations good to 5 to 50 km, no deposit maps, no soil measurements, no damage records, and rainfall reanalysis that smooths bursts. What would raise accuracy most is, in order, mapped deposits and scars for a handful of Pakistani events (to calibrate friction and the failure depth), field strength and soil-depth measurements in a few catchments, a landslide inventory with surveyed positions and times, and a damage survey after one event. If you can provide any of these, the calibration chapters can use them directly.
