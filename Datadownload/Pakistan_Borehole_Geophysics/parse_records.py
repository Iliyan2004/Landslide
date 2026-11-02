import csv
import re
import sys
from pathlib import Path

text_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

text = text_path.read_text(encoding="utf-8", errors="replace")

# Each hole starts at "Drilling Record ... DRILL HOLE UAK-n"
parts = re.split(r"Drilling Record\s+COALREAP\s+DRILL HOLE\s+UAK[-\s]*", text)[1:]

num = r"([0-9][0-9 ,.]*[0-9]|[0-9])"
rows = []

for part in parts:
    hole_match = re.match(r"\s*([0-9lI]+)", part)
    hole = hole_match.group(1).replace("l", "1").replace("I", "1") if hole_match else "?"

    def find(pattern, flags=re.S | re.I):
        m = re.search(pattern, part, flags)
        return re.sub(r"\s+", " ", m.group(1)).strip(" _") if m else ""

    topo = find(r"Topograp\S*\s+sheet number\s*_*\s*([0-9A-Za-z/ ]+?)_")
    northing = find(r"Grid reference:\s*([0-9 ]+?)_*\s*\(meters\)\s*Northing")
    easting = find(r"Northing\s*([0-9 ]+?)_*\s*\(meters\)\s*Easting")
    altitude = find(r"Altitude above mean sea level\s*([0-9. ]+?)_*\s*meters")
    rig = find(r"Drill rig type\s*([A-Za-z0-9\- ]+?)_")
    start = find(r"started\s*([A-Za-z]+ [0-9]{1,2}, ?[0-9]{4})")
    end = find(r"completed\s*([A-Za-z]+ [0-9]{1,2}, ?[0-9]{4})")
    depth = find(r"Total depth drilled\s*_*\s*([0-9.]+)")

    # Section 12 lists each geophysical log type with its interval
    logs = []
    section = re.search(r"12\. Geophysical Logs(.*?)13\. Remarks", part, re.S | re.I)
    if section:
        for line in section.group(1).splitlines():
            line = line.strip()
            if "from" in line.lower() and "(m)" in line.lower():
                logs.append(re.sub(r"\s+", " ", line.replace("_", " ")))

    rows.append({
        "hole": f"UAK-{hole}",
        "topo_sheet": topo,
        "grid_northing_m": northing.replace(" ", ""),
        "grid_easting_m": easting.replace(" ", ""),
        "altitude_msl_m": altitude.replace(" ", ""),
        "total_depth_m": depth,
        "drill_rig": rig,
        "geophysical_logs_run": " | ".join(logs),
        "source": "USGS OFR 90-304 (OCR; verify against PDF)",
    })

with out_path.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

print(f"{len(rows)} holes written to {out_path}")
