<!-- part: Part V - Rainfall Forcing -->
# Rainfall Sources

| Source | Resolution | Notes |
|---|---|---|
| Design storm | 15 min | Triangular (peak at mid-storm, SAILAB convention) or constant; user peak and duration |
| Open-Meteo forecast | hourly | Next 1 to 7 days; the same service SAILAB uses |
| Open-Meteo recent | hourly | Observed past days |
| ERA5-Land hindcast | hourly, 0.1 degree | Pick dates, or take the wettest 72 h at the location since a chosen year |
| IMERG half-hourly | 30 min, 0.1 degree | NASA GPM IMERG V07 from 2000 (monthly files on the server); each slot is a depth, returned as mm/h. Resolves short bursts better than hourly ERA5-Land; not yet compared with it for landslide skill |
| CHIRPS daily | daily, 5 km | A daily total is spread evenly over 24 h, because CHIRPS has no sub-daily information; intensities are therefore understated |
| Uploaded CSV | any | A time column (ISO or elapsed hours) and a rainfall column; unit is mm/h or mm per interval; negative, non-numeric or non-increasing times are rejected |

Rain is applied uniformly over the area. Every series is resampled to 15-minute steps with mass preserved (`to_step_depths`), and carries its source, start time, total, peak and duration into the run manifest. A series longer than 14 days is refused.

> ERA5-Land is a model reanalysis on a 0.1 degree grid: it smooths convective cloudbursts, which dominate Pakistani landslide triggers. Hindcasts with ERA5 therefore understate peak intensities at a point. This affects the validation in Ch. {{ch:rain_threshold_validation}} equally for events and controls, but it lowers the achievable skill.
