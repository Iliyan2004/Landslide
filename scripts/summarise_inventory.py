#!/usr/bin/env python3
"""Cleaned-inventory counts for the technical reference -> docs/validation/inventory_summary.json (reads one shapefile; takes a second)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "backend"))
from landslide.calibration import dataset as D   # noqa: E402
df = D.load(); s = D.summary(df)
s["rain_day_resolved"] = int(((df.trigger == "rain") & df.date.notna()).sum())
s["by_trigger_day_resolved"] = df[df.date.notna()].trigger.value_counts().to_dict()
Path(ROOT / "docs/validation/inventory_summary.json").write_text(json.dumps(s, indent=1, default=str)); print(s)
