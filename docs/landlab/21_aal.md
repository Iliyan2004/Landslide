# Average Annual Loss

Average annual loss (AAL) is the expected loss per year from landslides triggered by storms. The platform runs design storms of the chosen return periods (Ch. {{ch:design_storms_climate}}), each a full Tier 3 simulation with the same ground and strength settings, and takes the direct loss of each (Ch. {{ch:loss}}).

```
p = 1 / T                                       annual exceedance probability
AAL = integral of loss over p
  between the rarest and most frequent scenario:  trapezoid in p
  beyond the rarest (p < 1/Tmax):                 loss held at the rarest scenario's value
  between the most frequent scenario and p = 1:   loss falls linearly to zero at p = 1
```

A test checks the trapezoid against an analytic integral, and that zero loss gives zero AAL and more loss gives more.

> **The assumption that carries the number:** a T-year storm gives the T-year loss. That ignores antecedent wetness, the spatial pattern of rain, and the fact that most storms of a given depth cause no landslide at all; it also depends on the strength scenario, which is uncalibrated (Ch. {{ch:physics_calibration}}). Treat AAL as an order of magnitude for comparing places or options, not as an insurance figure. It also inherits every assumption in the damage and cost model.

Each return period is an expensive simulation, so the page asks for confirmation.

## First run on a real area

Gilgit, a 57 km2 area (7.8 by 7.3 km) around the test site (`scripts/run_area_demo.py`, `docs/validation/area_demo.json`), strength scenario "weak_clayey" at quantile 0.3 (the weakest standard preset with a graded response; the strong presets fail nothing in these storms and the fitted one over-predicts, Ch. {{ch:physics_calibration}}.6), losses valued as in Ch. {{ch:loss}} (structure, contents and crops, SAILAB valuation; about 3 times the earlier flat valuation), six return periods from 2 to 100 years, 6 hour storms from the observed IDF cube:

| Return period (y) | Storm depth (mm) | Failing area (km2) | Direct loss today (PKR) | Direct loss, SSP5-8.5 (PKR) |
|---|---|---|---|---|
| 2 | {{area_demo.json:aal_current.result.scenarios.0.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.0.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.0.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.0.loss_pkr|0}} |
| 5 | {{area_demo.json:aal_current.result.scenarios.1.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.1.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.1.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.1.loss_pkr|0}} |
| 10 | {{area_demo.json:aal_current.result.scenarios.2.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.2.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.2.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.2.loss_pkr|0}} |
| 25 | {{area_demo.json:aal_current.result.scenarios.3.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.3.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.3.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.3.loss_pkr|0}} |
| 50 | {{area_demo.json:aal_current.result.scenarios.4.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.4.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.4.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.4.loss_pkr|0}} |
| 100 | {{area_demo.json:aal_current.result.scenarios.5.depth_mm|0}} | {{area_demo.json:aal_current.result.scenarios.5.failing_km2|2}} | {{area_demo.json:aal_current.result.scenarios.5.loss_pkr|0}} | {{area_demo.json:aal_ssp585.result.scenarios.5.loss_pkr|0}} |
| **Average annual loss** | | | **{{area_demo.json:aal_current.result.eal_pkr|0}} PKR** | **{{area_demo.json:aal_ssp585.result.eal_pkr|0}} PKR** |

The climate factor for the 50 year, 24 hour rainfall under SSP5-8.5, 2036 to 2065, is {{area_demo.json:climate_ssp585_T50.result.factor|3}} (ensemble median over 8 CMIP6 models whose individual ratios range from 0.90 to 1.32). A factor that close to 1 with that spread is **no detectable change**, not a prediction of none.

Cautions that apply to these numbers:

- **The climate scenario changes the average annual loss by only {{area_demo.json:aal_ssp585.result.eal_pkr|0}} against {{area_demo.json:aal_current.result.eal_pkr|0}} PKR**, because the climate factor is 1.016. That is the honest result of a factor inside the model spread, not a finding that climate has no effect.
- The failing area is a fraction of a square kilometre for every return period ({{area_demo.json:aal_current.result.scenarios.0.failing_km2|2}} to {{area_demo.json:aal_current.result.scenarios.5.failing_km2|2}} km2), but the impacted area is about five times larger ({{area_demo.json:aal_current.result.scenarios.0.impacted_km2|1}} to {{area_demo.json:aal_current.result.scenarios.5.impacted_km2|1}} km2): runout carries debris to buildings well beyond the slope that failed, and the loss depends on which buildings it reaches, so it moves in steps.
- The AAL adds a frequent tail (storms more frequent than the 2 year, linear to zero at p = 1) that contributes {{area_demo.json:aal_current.result.parts.frequent_tail|0}} PKR of the total; the result is therefore sensitive to the 2 year loss.
- The earlier version of this table used the fitted weak preset and gave about 1 billion PKR with a larger spread of losses; the preset is the dominant uncertainty of every absolute number here.
- Every caveat above in this chapter applies: loss frequency is taken equal to rainfall frequency, with no antecedent wetness. Read the figure as an order of magnitude for this area, not a budget.
