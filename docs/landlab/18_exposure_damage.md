<!-- part: Part VI - Impacts and Risk -->
# Exposure and Damage

## 16.1 Exposure layers

| Layer | Source | Rule |
|---|---|---|
| Buildings | Google Open Buildings, local parquet tiles via DuckDB | Footprints whose centroid is inside the area; each takes the 3 x 3 cell maximum of flow depth and speed at its centroid; assumed height 6 m (3D only) |
| Roads | HOTOSM roads | A segment is blocked if flow depth at a vertex or at the segment midpoint is at least 0.5 m; blocked length is summed |
| Hospitals, schools | government shapefiles | Impacted if depth at the point is at least 0.3 m |
| Population | WorldPop 2025 via 05_risk | People per 90 m cell, rescaled by cell area; people in cells reached at 0.3 m or more |

## 16.2 Building damage

Dynamic pressure from the flow, a lognormal fragility for four damage states, and a floor from burial depth:

```
p (kPa) = rho v^2 / 1000,   rho = 1800 kg/m3
P(DS >= k) = Phi( ln(p / median_k) / 0.6 ),   medians 5, 15, 40, 100 kPa for DS1 to DS4
burial floor: depth >= 0.3 / 1 / 2 / 4 m  ->  at least DS1 / DS2 / DS3 / DS4
damage ratio by state: 0, 0.05, 0.20, 0.55, 1.00
```

The expected damage ratio is the probability-weighted ratio. Buildings in cells that never reach 0.3 m are DS0. **Every threshold above is an assumption inherited from the earlier prototype; none is calibrated to observed damage in Pakistan.**

## 16.3 3D colouring

The 3D viewer colours buildings by the expected damage from the depth reached so far (a curve of 0, 0.05, 0.20, 0.55 and 1.00 at 0, 0.3, 1, 2 and 4 m), so a building changes colour as the flow arrives. Roads turn when blocked.
