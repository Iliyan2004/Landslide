"""Financial loss, valued the way SAILAB values flood loss (loss_utils.py), so landslide and flood losses are on one footing.

Physical damage ratio per building comes from the landslide's own fragility (dynamic pressure and burial depth, engine/run.py): flood depth-damage curves do
not describe debris impact, so they are not used. The VALUATION is SAILAB's:
  structure loss = damage ratio x footprint area x storeys x max damage value
       storeys = max(1, building height / 3 m);  max damage value = Huizinga et al. (2017, JRC) Table 3-21, Asia residential, 111 EUR/m2 (2010 prices)
       converted at EUR_TO_PKR_RATE (a current-date conversion applied to a 2010-price figure: not inflation-adjusted)
  content loss   = 50% of structure loss (FEMA HAZUS residential content ratio)
  agricultural   = cropland cell area x damage fraction x JRC Asia agriculture value (0.03 EUR/m2)
Average annual loss integrates the per-return-period totals exactly as SAILAB's aal_utils does (engine/aal.py: trapezoid in annual exceedance probability, flat rare
tail, linear to zero at p = 1). Regional (Asia) values, not Pakistan-specific; Pakistan has no figure of its own in the source table."""
from __future__ import annotations

JRC_ASIA_MAX_DAMAGE_EUR_PER_M2 = {"Residential": 111.0, "Agriculture": 0.03}
EUR_TO_PKR_RATE = 322.5
PKR_RATE_NOTE = "EUR/PKR mid-market ~322.5 as used by SAILAB (loss_utils.py); refresh periodically"
MAX_DAMAGE_PKR_PER_M2 = {k: round(v * EUR_TO_PKR_RATE, 4) for k, v in JRC_ASIA_MAX_DAMAGE_EUR_PER_M2.items()}
CONTENT_TO_STRUCTURE_RATIO = 0.50
STOREY_HEIGHT_M = 3.0


def building_structure_loss(damage_ratio, footprint_m2, height_m):
    storeys = max(1.0, float(height_m) / STOREY_HEIGHT_M)
    return float(damage_ratio) * float(footprint_m2) * storeys * MAX_DAMAGE_PKR_PER_M2["Residential"]


def agricultural_loss(cropland_depth_m, cell_area_m2, full_loss_depth_m=0.5):
    """cropland_depth_m: debris depth on cropland cells (array). Damage fraction = min(1, depth / full_loss_depth_m): burial over half a metre is a total loss of
    the season's crop (an assumption; JRC's agriculture curve is for flood depth, not debris). Returns (loss_pkr, cells_damaged)."""
    import numpy as np
    d = np.nan_to_num(np.asarray(cropland_depth_m, float)); f = np.clip(d / full_loss_depth_m, 0.0, 1.0); f[d < 0.05] = 0.0
    return float(f.sum() * cell_area_m2 * MAX_DAMAGE_PKR_PER_M2["Agriculture"]), int((f > 0).sum())


def method_note():
    return ("Valuation as SAILAB (loss_utils.py): damage ratio x footprint x storeys (height/3 m) x JRC Asia residential "
            f"{JRC_ASIA_MAX_DAMAGE_EUR_PER_M2['Residential']} EUR/m2 x {EUR_TO_PKR_RATE} PKR/EUR; contents {int(CONTENT_TO_STRUCTURE_RATIO*100)}% of structure; "
            f"cropland {JRC_ASIA_MAX_DAMAGE_EUR_PER_M2['Agriculture']} EUR/m2. Damage ratios from the landslide fragility (dynamic pressure and burial, assumed medians 5/15/40/100 kPa). "
            "Building height is assumed 6 m (2 storeys) because footprints carry none. Regional Asia values, not Pakistan-specific; FX is current-date on 2010 prices.")
