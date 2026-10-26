@echo off
rem Serves the dashboard at http://localhost:8080/ (and on your network at your PC address, port 8080), with area-of-interest fetching.
cd /d "%~dp0"
python -X utf8 scripts\aoi_server.py --port 8080
