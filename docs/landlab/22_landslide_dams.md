# Landslide-Dam Screening

Where a runout deposit blocks a drainage line, a lake can form. The screening answers three questions about each blocking deposit: how big is the dam, how big a lake would it hold, and is it likely to be stable. It does **not** route a breach flood downstream: that is flood modelling, which is outside this product (the breach peak is given as a single number).

1. **Channels:** D8 flow accumulation on the pre-event DEM (pits filled); cells draining at least 0.5 km2 are channels. The drainage area is truncated at the edge of the analysed area, so it is a lower bound.
2. **Dams:** connected deposit of at least 2 m (3 x 3 neighbourhood) that sits on a channel. Height Hd is the greatest deposit thickness on the channel cells; volume Vd is the connected deposit volume.
3. **Stability:** the dimensionless blockage index of Ermini and Casagli (2003)

```
DBI = log10( Ab Hd / Vd )          Ab in m2, Hd in m, Vd in m3
likely stable if DBI < 2.75,  likely unstable if DBI > 3.08,  uncertain between
```

4. **Lake:** the crest is the highest post-event bed on the channel cells of the dam; the lake is the connected region upstream with pre-event bed below the crest, and its volume is the sum of (crest minus bed) times cell area.
5. **Breach peak:** `Qp = 0.607 V^0.295 h^1.24` (Froehlich 1995, an embankment relation, used here only as a screening number), with V the lake volume and h the crest minus thalweg height.

A synthetic valley test checks that a deposit across the channel is found, that DBI equals the formula and the lake is positive, that a deposit up the valley wall is not a dam, and that the Froehlich value reproduces the earlier prototype's 9,014 m3/s test case. Lake fill time needs an inflow, which is not known here, so it is not estimated.
