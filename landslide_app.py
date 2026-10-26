#!/usr/bin/env python3
"""Landslide platform web app.  python landslide_app.py  ->  http://<host>:5070"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from landslide.app.server import main
if __name__ == "__main__":
    main()
