# Calibration of the Physical Parameters

## 21.1 Idea

The infinite-slope plus Green-Ampt model has few parameters that matter: cohesion, friction angle, soil depth, saturated conductivity, root cohesion and the baseline water table. They are unmeasured, so they are calibrated: choose the values that make the model's predicted instability best separate reported events from controls, using the real ERA5 rain of each event day and the real terrain in each report's accuracy disc, then test on terrain and years that were held out.

## 21.2 Method

For each event and control, K = 256 random cells in the accuracy disc supply slopes; the preceding 14 days of ERA5 hourly rain give the Green-Ampt wetting front once per sample (it does not depend on the cell); each cell's FS at the final saturation follows from the closed form (Ch. {{ch:rain_triggered_failure}}.4); the score is minus the 10th percentile of FS over mobilisable cells. All samples are evaluated in one GPU batch, so thousands of parameter sets can be tried by differential evolution. Block cross-validation (spatial) and leave-one-year-out (temporal) guard against over-fitting; parameters are constrained to physically plausible ranges (the same bounds as `validate_ranges`).

## 21.3 Extension: spatially varying parameters

The server holds lithology (GLiM), soil texture (SoilGrids), land cover and NDVI. A lookup of cohesion and friction multipliers by lithology class, and of root cohesion by land cover, can be added, with the multipliers shrunk toward 1 so that a few reports cannot fit noise. This is only worth keeping if it improves the held-out score.

## 21.4 Result

144 rain-triggered reports located to within 10 km, each with matched control days at the same place and season, scored on 34 days of ERA5-Land rain (31 days of antecedent rain plus a 3-day storm window). Differential evolution fitted eleven parameters (the six strength and hydraulic values plus the five antecedent-wetness constants of Ch. {{ch:rain_triggered_failure}}.5) on four fifths of the spatial blocks and scored the fifth held out, five times.

| Quantity | Value |
|---|---|
| Held-out AUC, shipped defaults | {{physics_calibration.json:default.auc|3}} |
| Held-out AUC, defaults plus antecedent wetness at its initial constants | {{physics_calibration.json:default_with_antecedent.auc|3}} |
| Held-out AUC, calibrated | {{physics_calibration.json:calibrated.auc|3}} |
| Calibrated values (median over folds) | {{physics_calibration.json:calibrated.params_text}} |

The calibrated set beat the defaults by more than the 0.02 adoption margin, so the antecedent constants are the platform's defaults now (`engine/antecedent.py`) and a strength preset "calibrated_reports" carries the fitted soil depth (2.5 m), cohesion (0.9 kPa) and friction (29.9 degrees).

Read this with care:

- Most of the gain comes from the fitted strength being weak (cohesion near the bottom of its allowed range) and from the antecedent terms together; the antecedent wetness at its initial constants added nothing on its own. The fit says what makes the model rank *reported* landslide days above ordinary days, not what the true soil strength is. The fitted conductivity, water table and root cohesion sit at the edges of their ranges and are not carried into the presets: they are partly absorbing errors elsewhere (ERA5 smoothing the bursts, report bias).
- Held-out folds differ a lot (0.58 to 0.72 for the first two folds) because there are only 144 events, so the 0.68 has a wide interval.
- The skill is relative: it ranks days, it does not predict how many landslides occur.

## 21.5 Second run, with topographic wetness and suction

The same fit repeated with two more parameters (wetness exponent, suction; Ch. {{ch:rain_triggered_failure}}.7) gives held-out AUC {{physics_calibration.json:calibrated.auc|3}} against 0.683 before: no improvement, and the added parameters are not identifiable between folds. The first fit (0.683, the antecedent constants and the "calibrated_reports" preset) is the one adopted in the code; the file `physics_calibration_v1_no_wetness_suction.json` keeps it.
