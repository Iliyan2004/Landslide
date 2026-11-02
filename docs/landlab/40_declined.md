# Considered and Declined

- **Coupling with flood modelling.** Declined by the owner: LANDLAB and SAILAB stay separate products. Debris flows are not run through a water solver.
- **Using the national ML susceptibility as a predictor in the validation models.** It was trained on the inventory; using it would leak the answer. It is shown as a labelled optimistic reference only.
- **Bilinear resampling of population.** Counts are not intensities; see Ch. {{ch:chronicle}} (#1).
- **Promoting year-only dates to a day.** Invents precision that would corrupt the rainfall validation.
- **A Pakistan-specific I-D threshold.** Fitted, but no better out of sample than the published Guzzetti curve (Ch. {{ch:rain_threshold_validation}}.4), so not adopted.
- **Absolute landslide probabilities.** Not identifiable from a report inventory.
- **A temperature guard on GPU jobs.** Dropped by the owner's decision (Ch. {{ch:architecture}}.3).
- **Interactive whole-country physics.** Meaningless at the needed cell size (Ch. {{ch:terrain_parameters}}.1); replaced by the tiled national product.
- **External multiphase runout engines (r.avaflow and similar).** Not available on the server; the in-house solver is verified but uncalibrated, and this is stated wherever it is used.
- **Raising the inventory with downloaded catalogues.** No further catalogue was found on the server, and none was downloaded without the owner's say-so.
- **Routing a landslide-dam breach flood downstream.** That is flood modelling; the dam screening stops at formation, stability, lake volume and a breach peak (Ch. {{ch:landslide_dams}}).
- **An areal reduction factor on design storms.** The constants are not available from a source on the server; point rainfall is used and is conservative for the areas run.
- **A surrogate model for barrier placement.** Not trusted at this sample size; every candidate is a real simulation under a hard budget.
- **Default wall costs.** No cost data exist here; the optimiser takes the cost from the user and says what happens at zero.
- **Filling in geology strength values from intuition.** The 16 geology units are colour classes with guessed lithology; invented values would look like data. Multipliers stay 1.0 until calibration.
- **Real-time seismic wave speed in the animation.** Physically correct and invisible; the rings are time-scaled and say so.
