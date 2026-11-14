=== SECTION 1: OVERVIEW AND CONVENTIONS ===
PROJECT: Burning Activity Calendar (hackathon, static web app, no backend server)
GOAL: Harmonize MODIS (2000+) and VIIRS S-NPP (2012+) active fire hotspots into one
consistent record. The user draws a rectangle on a map and sees a calendar heatmap,
climatology, anomalies and critical weeks. A live layer shows near-real-time hotspots
of the last 5 days and an early-warning banner compares them with normal activity.
REGION: Pakistan + Indian Punjab/Haryana/Delhi (lat 23 to 37, lon 60 to 78)
RUNS ON: Linux Mint, Python 3 with pandas/numpy/matplotlib/requests. Frontend: plain HTML/CSS/JS,
Leaflet 1.9.4, Leaflet.draw 1.0.4, Plotly.js 2.35 loaded from CDN. No frameworks, no modules.
The website folder is docs/ (not web/). Paths in the website are relative to docs/.

CONVENTIONS (never change):
- Grid: 0.25 degree. Cell id uses cell CENTER:
    cell_lat = floor(lat/0.25)*0.25 + 0.125 ; cell_lon = floor(lon/0.25)*0.25 + 0.125
- Time bin: weekly. week_start = the MONDAY of that week, format YYYY-MM-DD.
- Week of year = ISO week number (1 to 53), computed from the week_start date.
- VIIRS_START_WEEK = 2012-03-05. Weeks before it use scaled MODIS; this week and later use VIIRS.
- Sensor names in files: "modis" and "viirs" (lowercase).
- Confidence filter everywhere: MODIS >= 30; VIIRS keep "n" and "h", drop "l".
- Live source: FIRMS Area API, source VIIRS_SNPP_NRT, last 5 days. Key is FIRMS_MAP_KEY in .env.

=== SECTION 2: DATA FILES ===
1. data/raw/modis/*.csv and data/raw/viirs/*.csv  (NASA FIRMS archive downloads)
   MODIS columns: latitude, longitude, brightness, scan, track, acq_date, acq_time,
     satellite, instrument, confidence (number 0-100), version, bright_t31, frp, daynight, type
   VIIRS columns: latitude, longitude, bright_ti4, scan, track, acq_date, acq_time,
     satellite, instrument, confidence (letters l/n/h), version, bright_ti5, frp, daynight, type
   (the "type" column may be missing; handle that)
2. data/processed/weekly_counts.csv
   columns: cell_lat, cell_lon, week_start, sensor, count, frp_sum
3. data/processed/harmonization.json
   {"method": "ratio of VIIRS to MODIS weekly totals per ISO week-of-year, overlap period only",
    "overlap_start": "2012-03-05", "overlap_end": "YYYY-MM-DD",
    "factor_by_week_of_year": {"1": 0.95, "2": 1.1, ... "53": 1.0}}
4. docs/data/fire_data.json
   {"meta": {"grid": 0.25, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "viirs_start": "2012-03-05"},
    "weeks": ["YYYY-MM-DD", ...],              // every Monday, continuous, no gaps
    "cells": [[cell_lat, cell_lon], ...],
    "records": [[cell_index, week_index, harmonized_count], ...]}   // sparse, only nonzero
   cell_index points into "cells", week_index points into "weeks". Counts rounded to 1 decimal.
5. docs/data/live_hotspots.json
   {"fetched_utc": "YYYY-MM-DDTHH:MM:SSZ", "source": "VIIRS S-NPP NRT", "days": 5,
    "points": [[lat, lon, "YYYY-MM-DD", "HHMM", frp], ...]}
   acq_time is a 4-character zero-padded string such as "0205" (UTC). frp is a number.

=== SECTION 3: JAVASCRIPT CONTRACT ===
bounds = {south, west, north, east}
docs/js/map.js        initMap(mapDivId, onAOIChange) -> calls onAOIChange(bounds) when the user
                      draws or edits a rectangle; calls onAOIChange(null) when it is deleted
                      showLivePoints(points) -> draws live hotspots as small circle markers, replacing old ones
                      clearLivePoints()
docs/js/analytics.js  loadFireData(url) -> Promise(data)
                      isoWeek(dateString) -> number 1..53
                      getAOISeries(data, bounds) -> {weeks:[YYYY-MM-DD], values:[number], cellCount:number}
                      getClimatology(series) -> {weekOfYear:[1..53], mean:[], std:[]}
                      getAnomalies(series, clim) -> {weeks:[], values:[], zscores:[]}
                      getCriticalWeeks(series, clim, n) -> [{week, value, zscore}] sorted by zscore desc
                      getCalendarMatrix(series) -> {years:[], weeks:[1..53], z:[[...]]} (null where no data)
                      getPeakSeason(clim) -> {startWeek, endWeek, peakWeek}
                      loadLiveData(url) -> Promise(live) ; resolves null if the file is missing or invalid
                      getLiveInAOI(live, bounds) -> {points:[], count:number, latestDate, latestTime}
                      getEarlyWarning(clim, live, liveAOI) -> {level, ratio, liveCount, expected, days,
                                  weekOfYear, message}   level is "normal", "elevated", "high" or "nodata"
docs/js/charts.js     drawCalendarHeatmap(divId, matrix), drawClimatology(divId, clim, peak),
                      drawAnomalies(divId, anomalies)
docs/js/main.js       connects everything
HTML element ids in index.html: map, live-status, warning, status, summary,
                      calendar-chart, climatology-chart, anomaly-chart
Scripts load order in index.html: map.js, analytics.js, charts.js, main.js