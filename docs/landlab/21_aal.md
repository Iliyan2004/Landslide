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

Each return period is an expensive simulation, so the page asks for confirmation. **Not yet run on real data.**
