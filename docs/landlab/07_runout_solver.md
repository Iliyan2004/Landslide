# The Runout Solver

## 7.1 Scheme

The failed soil becomes a depth-averaged flow. The solver is the local-inertial shallow-water scheme of Bates et al. (2010) on a staggered grid (discharge per unit width q on cell faces) with a Voellmy basal resistance, applied semi-implicitly. It is the scheme that the platform's earlier in-browser solver verified (docs/VALIDATION_REPORT tests V4 to V7), now in compiled code.

```
face depth        h_f = max(eta_A, eta_B) - max(z_A, z_B),   eta = z + h        (no flux if h_f <= 0.02 m)
momentum          q* = q - g h_f dt (eta_B - eta_A)/dx
Voellmy friction  m  = |q*| / (1 + dt g |q*| / (xi h_f^2))                     turbulent term
Coulomb           m  = max(0, m - h_f mu_eff g cos(theta) dt)                  dry friction on the slope
                  q  = sign(q*) min(m, 25 h_f)
mu_eff            = mu (1 - 0.6 lambda)                                         pore-pressure fluidisation
limiter           outflow of a cell is scaled so it cannot lose more than it holds
continuity        h_new = h - dt/dx (net flux)
```

Velocity is the average of face velocities (faces deeper than 5 cm), capped at 30 m/s; only cells deeper than 0.3 m report a velocity.

## 7.2 Release, entrainment and fluidisation

- **Release:** a failing cell's soil thickness (times a user factor, default 1) is moved from the bed to the flow: the bed drops by the thickness and the flow gains it, so no mass is created.
- **Entrainment:** where depth exceeds 0.5 m and speed exceeds 2 m/s, the bed gives up soil at `0.0015 v dt min(1, h/2)` until a user-set erodible depth (default 0.5 m, cells that did not fail) is exhausted. The bed lowers by what the flow gains.
- **Fluidisation:** rain-triggered flows use a pore-pressure ratio lambda of 0.6, which lowers the friction coefficient by 36%; earthquake-triggered flows use zero.

## 7.3 Flow types

The friction parameters are **scenario values by flow type, not calibrated to any event** (calibration is planned, Ch. {{ch:runout_calibration}}):

| Type | mu | xi (m/s2) |
|---|---|---|
| Debris flow / mudflow | 0.12 | 200 |
| Earth / soil flow | 0.20 | 250 |
| Shallow slide, short runout | 0.30 | 300 |

## 7.4 Time stepping and frames

The step is the smaller of the CFL step and 0.2 s. The cap matters: the semi-implicit friction is first order in time, and at 0.5 s the steady speed on a uniform slope was 12% low (12.2 against 13.9 m/s), at 0.1 s it is 2.4% low. Releases happen at their failure times; the solver advances only while something is moving and jumps over quiet periods (after 300 s at rest). The animation window runs from two minutes before the first failure to 30 minutes after the last, sampled at 120 evenly spaced frames.

## 7.5 Verification (not validation)

| Check | Result |
|---|---|
| Closed-domain mass conservation | drift 0 to machine precision |
| Lake at rest over rough ground | flux exactly 0 |
| Steady speed on a 0.5 slope, mu 0.2, xi 400, h 1.5 m | within 5% of sqrt(xi h (tan b - mu cos b)) at dt 0.1 s |
| Rest below the friction slope | interior flux 0 |
| Entrainment | bed loss plus flow gain sums to 0 |
| GPU against CPU | agree to 1e-15 (float64) and 2e-6 m (float32) |

These show the code solves its equations. They do not show it predicts real runout; see Ch. {{ch:runout_calibration}}.
