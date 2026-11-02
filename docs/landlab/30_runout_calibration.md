# Check of the Runout Parameters

## 22.1 What data exists

The inventory has almost no volumes (one record) and no runout lengths or deposit areas, so the friction coefficients mu and xi cannot be fitted to Pakistani events. What can be done:

1. **Match published empirical relations.** The Corominas (1996) fits of height drop H against runout length L, H = a L^b, with debris flows 1.109 L^0.857, landslides 2.606 L^0.669, and rock avalanches 1.758 L^0.859, give an expected travel angle for a given volume class. mu and xi per flow type are tuned so simulated reach angles over synthetic and real slopes fall inside the scatter of these relations.
2. **Earthquake ground motion** can be checked against USGS ShakeMaps of past Pakistani earthquakes (done, Ch. {{ch:earthquake_failure}}.2).
3. **Deposit shape** can be scored (IoU, depth error) only if the owner supplies mapped deposits, for example from field surveys or high-resolution imagery.

## 22.2 Result

Synthetic channelised slopes (V-shaped valley, concave profile, heights 500, 800 and 1200 m, volumes 10^4, 10^5 and 10^6 m3) were released as a slab and run to rest on the GPU. For each, H is the elevation drop from the source to the furthest cell with depth over 0.3 m, L the path length, and the ratio is H(simulated) divided by the Corominas H for that L. A ratio of 1 reproduces the relation; the published scatter is about a factor of 2.

| Flow type, as shipped | mu, xi | Median ratio | Range over the 9 cases |
|---|---|---|---|
| Debris flow | 0.12, 200 | {{runout_calibration.json:types.debris_flow.median_ratio|2}} | 0.43 to 1.03 |
| Landslide (shallow slide) | 0.30, 300 | {{runout_calibration.json:types.landslide.median_ratio|2}} | 1.03 to 2.22 |

Both medians and all nine cases of each type lie inside a factor of 2.3 of the relation, but the two types sit on opposite sides: the debris flow is somewhat too long for its drop in the wettest sense (ratio below 1) and the shallow slide too short, and the shallow-slide ratio grows with volume (1.0 at 10^4 m3, about 2.1 at 10^6). So **mu and xi were left unchanged**: the synthetic valley is not a Pakistani valley, the Corominas relations are for a world sample with their own factor-of-2 scatter, and tuning two coefficients to one synthetic geometry would give false precision. The result says the solver's runouts are in the right range, not that they are calibrated. Any real calibration needs mapped deposits from the owner.

## 22.3 Why the friction was not tuned further

Because the simulated debris-flow runouts sit about 1.5 times longer than the Corominas median for the same drop (a median ratio of {{runout_calibration.json:types.debris_flow.median_ratio|2}}, which is a runout about 1.5 times the median relation's for the same drop) and the shallow-slide ones about half as long, a tuning of mu to the median was started. One evaluation of the debris-flow friction moved the median ratio only from 0.71 to 0.74 when mu rose from 0.12 to 0.13, so matching the median would need a friction near that of the shallow slide, which would erase the difference between the two flow types on the strength of one synthetic channel. It was stopped and the shipped values kept. The large flow depths and impacted areas seen in early runs came from the strength preset, not from the friction (Ch. {{ch:physics_calibration}}.6), and are handled there.
