# Calibration of the Spatial Ground

## 22.1 Data

Four layers were downloaded for this chapter (`datasets/external/`, `scripts/download_ground_data.py`, `build_glim_pk.py`, `build_vs30_pk.py`):

| Layer | Source | Use |
|---|---|---|
| Lithology | GLiM v1.1 (Hartmann and Moosdorf 2012), 16 first-level classes, grouped into six strength groups | cohesion and friction multipliers |
| Soil texture | SoilGrids 2.0, clay, sand and coarse fragments, mean of 5 to 60 cm, 250 m | cohesion and friction multipliers |
| Depth to bedrock | SoilGrids 2017 (BDTICM), 250 m (median 39 m over Pakistan) | slip-depth cap |
| Vs30 | USGS global grid (Heath et al. 2020) | earthquake site term (Ch. {{ch:earthquake_failure}}) |

## 22.2 Method

Events are the {{ground_calibration.json:n_events|0}} inventory reports (rain, unknown and earthquake triggers) in the northern study area; controls are ten random points per event with the same location-accuracy radii. Each point is scored on 160 cells of its disc by the 90th percentile of the physical instability index (how little saturation brings the cell to FS = 1) computed with that cell's own cohesion, friction, depth and roots. Variants add one layer at a time to a three-parameter base fit (c, phi, z). Every variant is fitted by differential evolution on four fifths of the 1 degree blocks and scored on the fifth, five times; ground coefficients are shrunk toward neutral by a small penalty.

## 22.3 Result

| Variant | Held-out AUC |
|---|---|
| Mean slope, no fit | {{ground_calibration.json:slope_mean_auc_no_fit.auc|3}} |
| Base physics, shipped values | {{ground_calibration.json:variants.base.auc_default_heldout|3}} |
| Base physics, fitted | {{ground_calibration.json:variants.base.auc_heldout|3}} |
| plus lithology | {{ground_calibration.json:variants.+lithology.auc_heldout|3}} |
| plus soil texture | {{ground_calibration.json:variants.+texture.auc_heldout|3}} |
| plus bedrock-depth cap | {{ground_calibration.json:variants.+regolith.auc_heldout|3}} |
| plus land-cover roots | {{ground_calibration.json:variants.+roots.auc_heldout|3}} |
| all layers | {{ground_calibration.json:variants.all.auc_heldout|3}} |

Soil texture is the only layer that clearly helps (0.65 against 0.56 for the base fit), adding all layers does worse than texture alone (it over-fits), and the folds disagree widely (texture ranges from 0.57 to 0.72). The fitted texture coefficients put *more* clay with *lower* cohesion (a_c about -1.5, at its bound) and more sand with higher friction: that is a statistical association with reported landslide places, which sit in particular valleys and road corridors, and it is not a soil-mechanics result. Texture is therefore left **off** by default (`configs/ground_classes.yaml` is still neutral). The fitted values are in `ground_calibration.json` for a user who wants to enable them as a sensitivity run.

Lithology (0.59) and the bedrock-depth cap (0.59) each add about 0.03 over the base fit, with folds that disagree (lithology 0.50 to 0.71), which is within the noise of 600 events. Neither is adopted. The inventory has no records on several lithology groups, so their weights cannot be estimated.
