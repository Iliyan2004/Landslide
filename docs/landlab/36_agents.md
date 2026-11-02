# Autonomous Monitoring Agents

The brief for this section asked for agents that manage continuous data streams, preprocess and diagnose workflows, detect interruptions, activate fallbacks, and keep validating and correcting forecasts. Part of that applies to LANDLAB and part does not, and the agents here are **rule-based programs, not language models**: each is a small deterministic procedure with a log, so it can be tested and explained (`app/agents.py`, 6 unit tests).

## 36.1 What applies and what does not

| Brief | Applies? | What was built |
|---|---|---|
| Continuous data stream management | Partly. The platform has one live stream (Open-Meteo rainfall for the watches and forecast runs); the terrain, land cover, population and inventory are static files. | Every live fetch reports success or failure to the interruption agent; `/api/agents/status` shows each feed's counts and consecutive failures. |
| Detect data interruptions, activate fallbacks | Yes | Open-Meteo calls retry three times with back-off, then fall back to the last good response for the same 0.1 degree point if it is under 6 hours old, marked `stale_cache` with its age so the page and the watch say so. Outages and recoveries are logged. |
| Preprocessing and workflow diagnostics | Partly. Preprocessing is a fixed pipeline, not a stream. | A health snapshot checks the required data files, the age of the ERA5 archive, the GPU and its free memory, disk space and the live feeds. Failed physics jobs are classified (user input, GPU, network, other): GPU and network failures are retried once (CPU solver, or a pause) and the recovery is written onto the result; user-input and unknown errors are not retried because a repeat would fail the same way. |
| Evaluate and optimise models through forecast validation and error correction | Yes, for the rain forecast that drives the watches | Each monitored forecast is stored and later scored against what Open-Meteo reports as observed for the same hours; a bias factor per lead day, shrunk toward 1, scales the forecast before the watch threshold is tested. |
| Continuous learning of the landslide model itself | No | The physics and thresholds are calibrated offline against the inventory (Ch. {{ch:physics_calibration}}); there is no stream of confirmed landslides or damage to learn from, so nothing is adjusted automatically. |

## 36.2 The forecast back-test

Open-Meteo's previous-runs service archives forecasts made 1 and 2 days ahead. For 40 random points in northern Pakistan over 15 June to 30 September 2026, those forecasts were compared with the Open-Meteo archive (ERA5-based reanalysis rain, **not gauges**) on daily totals (`scripts/validate_forecasts.py`, `docs/validation/forecast_audit.json`).

| Lead | Bias (forecast / observed) | Mean absolute error (mm/day) | Correlation | Detection of a 20 mm/day event | False alarms |
|---|---|---|---|---|---|
| 1 day | {{forecast_audit.json:by_lead_day.1.bias_ratio|2}} | {{forecast_audit.json:by_lead_day.1.mae_mm|1}} | {{forecast_audit.json:by_lead_day.1.corr|2}} | {{forecast_audit.json:by_lead_day.1.POD|pct}} | {{forecast_audit.json:by_lead_day.1.FAR|pct}} of alerts |
| 2 days | {{forecast_audit.json:by_lead_day.2.bias_ratio|2}} | {{forecast_audit.json:by_lead_day.2.mae_mm|1}} | {{forecast_audit.json:by_lead_day.2.corr|2}} | {{forecast_audit.json:by_lead_day.2.POD|pct}} | {{forecast_audit.json:by_lead_day.2.FAR|pct}} of alerts |

What this says: the forecasts run 8% (1 day) and 12% (2 days) wetter than the reanalysis, they track the daily pattern moderately (correlation about 0.65), and they are **poor at heavy-rain days**: of the 72 days of 20 mm or more, a 1-day forecast flagged 42% and a 2-day forecast 33%, and about two thirds of the alerts at that level were false. The correction applied to the watch is therefore small (factor 0.93 at one day, 0.90 at two) and cannot repair that. The 0-day row (not shown) is perfect by construction because the archive is built from the same short-lead analysis, so it tests nothing; it is excluded from the conclusions, and the lead-0 factor stays at 1. Because the truth is itself a model, the correction removes forecast drift from the analysis, not bias against real rainfall; against gauges (none on the server) the picture could differ.

## 36.3 Live audit and the event log

The watches store every forecast they issue. Every 30 minutes the audit agent scores the forecasts whose horizon has passed and updates the live bias factors, which take precedence over the back-test prior once they exist. Events (feed down and recovered, job errors and recoveries, audits, health changes) are kept in `datasets/state/agents/events.jsonl` (the last 2,000) and shown at `/api/agents/status`; a status chip in the page header links to it. At the time of writing the health snapshot reports one real problem: the ERA5-Land archive on the server ends on {{agents_status.json:era5.last_time}}, so hindcasts of storms after that date (and the calibration of any recent event) are not possible until the archive is extended.

## 36.4 Limits

The interruption agent can only keep a watch running on a feed that returns at all: when Open-Meteo is down for more than 6 hours, the watch reports the error rather than guessing, and there is no second forecast provider to switch to. Recovery from a GPU failure repeats the whole run on the CPU, which is slower, and a run that fails for a reason not in the list is reported, not repaired. The agents do not fix the model: they keep it fed, running and honestly scored.
