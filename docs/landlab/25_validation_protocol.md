<!-- part: Part VIII - Calibration and Validation -->
# Calibration and Validation Protocol

## 18.1 What can and cannot be validated

| Question | Can it be checked here? | How |
|---|---|---|
| Does the code solve its own equations? | Yes | Unit tests and analytic checks (verification, Ch. {{ch:runout_solver}}.5) |
| When does rain trigger landslides in Pakistan? | Partly | Dated rain-triggered reports against matched control days (Ch. {{ch:rain_threshold_validation}}) |
| Where are slopes prone? | Partly | Reports against random places, scored over each report's accuracy disc (Ch. {{ch:spatial_validation}}) |
| Are soil strength parameters right? | Only through their effect on the two items above | Calibration against reports with block cross-validation (Ch. {{ch:physics_calibration}}) |
| Is simulated runout and depth right? | Only against published empirical relations | No mapped deposits exist locally (Ch. {{ch:runout_calibration}}) |
| Is building damage or loss right? | **No** | No damage records exist locally |

## 18.2 Rules that apply to every experiment

1. **Controls are matched, not convenient.** Temporal controls are the same place on other days of the same season; spatial controls are scored over discs with the same radius distribution as the events, so a large location uncertainty cannot manufacture skill.
2. **Positional uncertainty is carried, not ignored.** A report with a stated accuracy of r km only says the slide lies somewhere within r km.
3. **Honest cross-validation.** Temporal models are cross-validated leaving one year out; spatial models leave out whole 1 degree blocks, repeated with different fold assignments. A random split lets neighbouring points leak between train and test and inflates AUC.
4. **No leakage.** The national ML susceptibility map was trained on these reports; it is never used as a feature in a cross-validated model, and its own scores on them are labelled optimistic.
5. **Uncertainty is shown.** AUC intervals come from a cluster bootstrap (an event and its controls resample together).
6. **No absolute probabilities.** Reports depend on population and roads. Outputs are relative likelihoods, not annual probabilities.
7. **Results are written to JSON** (`docs/validation/*.json`) and this document reads them, so numbers cannot drift.

## 18.3 The inventory after cleaning

Duplicates (same place within 5 km and the same day, or the same stated year for undated records) are merged keeping the most precisely located record. Day-resolved dates are used for temporal work; year-only and month-only strings are not promoted to a day. Trigger classes (rain, earthquake, GLOF, snow, anthropogenic, unknown) come from the cause fields. Location accuracy is parsed from the stated accuracy text, and a record with none is given 25 km and flagged.

| | Count |
|---|---|
| Unique events | {{inventory_summary.json:records|0}} |
| With a day-resolved date | {{inventory_summary.json:dated|0}} |
| Rain-triggered, day-resolved | {{inventory_summary.json:rain_day_resolved|0}} |
| Accurate to 1 km or better | {{inventory_summary.json:radius_le_1km|0}} |
| Accurate to 5 km or better | {{inventory_summary.json:radius_le_5km|0}} |
