# Estimated Direct Loss

Loss is valued the way SAILAB values flood loss (`loss_utils.py` there, `engine/loss.py` here), so a landslide loss and a flood loss are on the same footing and the same average-annual-loss method (Ch. {{ch:aal}}) applies to both.

## 19.1 Valuation

```
structure loss = damage ratio x footprint area x storeys x maximum damage value
  storeys               = max(1, building height / 3 m)
  maximum damage value  = 111 EUR/m2 x 322.5 PKR/EUR = 35,798 PKR/m2      (Huizinga et al. 2017, JRC EUR 28552, Table 3-21, Asia residential, 2010 prices)
content loss    = 50% of structure loss                                   (FEMA HAZUS residential content ratio)
agricultural    = cropland cell area x damage fraction x 0.03 EUR/m2 x 322.5   (JRC Asia agriculture)
direct loss     = structure + content + agriculture
```

What differs from the flood method, and why:

- The **damage ratio** is the landslide's own, not a flood depth-damage curve. A flood curve describes slow inundation; debris destroys by dynamic pressure and burial. Each building takes the maximum flow depth and speed of the surrounding cells, the dynamic pressure `rho v2 / 2` (rho = 1,800 kg/m3) is mapped to damage states with lognormal fragility medians of 5, 15, 40 and 100 kPa (dispersion 0.6), a burial depth sets a minimum state (0.3, 1, 2 and 4 m), and the expected ratio uses 0, 0.05, 0.20, 0.55 and 1.0 for the five states. **All of these are assumed; none is calibrated** to a Pakistani event.
- The **damage fraction on cropland** is `min(1, debris depth / 0.5 m)`: half a metre of burial is taken as a total loss of the crop. JRC's agriculture value (0.03 EUR/m2, about 10 PKR/m2) is tiny against buildings, so crops rarely matter in the total.
- **Building height** is not in the footprint dataset; 6 m (two storeys) is assumed for every building, which, with the 50% contents, makes the same damage cost about 3 times what the earlier flat valuation (35,000 PKR/m2, one floor, no contents) gave. Loss figures from before this change are not comparable with the ones here.

## 19.2 Limits

The unit value is a regional (Asia) average: Pakistan has no figure of its own in the source table. The exchange rate is a current-date conversion applied to a 2010-price figure, not inflation-adjusted. Footprint area times two storeys overstates single-storey kacha houses and understates multi-storey urban blocks, which is why housing type from the census (a planned addition) matters. Indirect losses (road closure days, business interruption, lives) are **not** estimated. The result is an order-of-magnitude figure for comparing scenarios, not an insured value.
