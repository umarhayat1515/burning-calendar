"""
d_export.py
Exports the harmonized weekly fire counts as a compact sparse JSON file
for the website.

Run from the project root:
    python scripts/d_export.py

Inputs : data/processed/weekly_counts.csv
         data/processed/harmonization.json
Output : docs/data/fire_data.json
"""

import datetime
import json
import os
import sys

import numpy as np
import pandas as pd

# ---------- Configuration ----------
IN_COUNTS = os.path.join("data", "processed", "weekly_counts.csv")
IN_HARMONIZATION = os.path.join("data", "processed", "harmonization.json")
OUT_FILE = os.path.join("docs", "data", "fire_data.json")

GRID = 0.25
VIIRS_START_WEEK = pd.Timestamp("2012-03-05")  # first week that uses VIIRS
MIN_COUNT = 0          # drop records whose rounded count is below this (try 0.5 or 1 to shrink the file)
MAX_SIZE_MB = 25       # print a warning above this size


def main():
    # ---------- Load inputs ----------
    for path in (IN_COUNTS, IN_HARMONIZATION):
        if not os.path.exists(path):
            sys.exit(f"ERROR: {path} not found. Run the earlier scripts first.")

    df = pd.read_csv(IN_COUNTS)
    df["week_start"] = pd.to_datetime(df["week_start"])

    with open(IN_HARMONIZATION) as fh:
        factors = json.load(fh)["factor_by_week_of_year"]  # keys are "1".."53"

    # ---------- Step 4 (part 1): partial-week limits ----------
    # Both the first week and the last VIIRS week can be partial weeks,
    # so only weeks from first_week + 7 days to last_week - 7 days are used.
    first_week = df["week_start"].min()
    viirs_rows = df[df["sensor"] == "viirs"]
    if viirs_rows.empty:
        sys.exit("ERROR: no VIIRS rows found.")
    last_week = viirs_rows["week_start"].max()

    range_start = first_week + datetime.timedelta(days=7)
    range_end = last_week - datetime.timedelta(days=7)
    if range_start > range_end:
        sys.exit("ERROR: the usable date range is empty.")

    # ---------- Steps 1 and 2: harmonize ----------
    # MODIS before the VIIRS start: scale by the week-of-year factor
    modis = df[(df["sensor"] == "modis") & (df["week_start"] < VIIRS_START_WEEK)].copy()
    iso_week = modis["week_start"].dt.isocalendar().week.astype(int)
    modis_factor = iso_week.astype(str).map(factors).astype(float).fillna(1.0)  # 1.0 if a key is missing
    modis["harmonized"] = modis["count"] * modis_factor

    # VIIRS from the VIIRS start on: use the count as it is
    viirs = df[(df["sensor"] == "viirs") & (df["week_start"] >= VIIRS_START_WEEK)].copy()
    viirs["harmonized"] = viirs["count"].astype(float)

    # All other rows (e.g. VIIRS before its start, MODIS after) are ignored
    both = pd.concat([modis, viirs], ignore_index=True)

    # ---------- Step 3: sum duplicates of the same cell-week ----------
    both["cell_lat"] = both["cell_lat"].round(3)
    both["cell_lon"] = both["cell_lon"].round(3)
    merged = both.groupby(["cell_lat", "cell_lon", "week_start"], as_index=False)["harmonized"].sum()

    # ---------- Step 4 (part 2): discard records outside the usable range ----------
    merged = merged[(merged["week_start"] >= range_start) & (merged["week_start"] <= range_end)]

    # ---------- Step 5: continuous list of every Monday (no gaps) ----------
    weeks = pd.date_range(range_start, range_end, freq="7D")

    # ---------- Step 6: rounding, filtering, indexes ----------
    merged = merged.copy()
    merged["harmonized"] = merged["harmonized"].round(1)
    merged = merged[(merged["harmonized"] > 0) & (merged["harmonized"] >= MIN_COUNT)]
    if merged.empty:
        sys.exit("ERROR: no records left after filtering.")

    # Unique cells sorted by latitude, then longitude
    cells = (merged[["cell_lat", "cell_lon"]].drop_duplicates()
             .sort_values(["cell_lat", "cell_lon"]).reset_index(drop=True))
    cells["cell_index"] = np.arange(len(cells))
    merged = merged.merge(cells, on=["cell_lat", "cell_lon"], how="left")

    # Week index = number of whole weeks since the first week in the list
    merged["week_index"] = ((merged["week_start"] - weeks[0]).dt.days // 7).astype(int)

    merged = merged.sort_values(["week_index", "cell_index"])

    # ---------- Step 7: write the JSON ----------
    out = {
        "meta": {
            "grid": GRID,
            "start": weeks[0].strftime("%Y-%m-%d"),
            "end": weeks[-1].strftime("%Y-%m-%d"),
            "viirs_start": VIIRS_START_WEEK.strftime("%Y-%m-%d"),
        },
        "weeks": [w.strftime("%Y-%m-%d") for w in weeks],
        "cells": [[float(lat), float(lon)] for lat, lon in zip(cells["cell_lat"], cells["cell_lon"])],
        "records": [[int(c), int(w), float(v)] for c, w, v in
                    zip(merged["cell_index"], merged["week_index"], merged["harmonized"])],
    }

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))

    # ---------- Step 8: summary ----------
    size_mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f"Weeks:   {len(out['weeks']):,}")
    print(f"Cells:   {len(out['cells']):,}")
    print(f"Records: {len(out['records']):,}")
    print(f"First week: {out['meta']['start']}")
    print(f"Last week:  {out['meta']['end']}")
    print(f"MIN_COUNT:  {MIN_COUNT}")
    print(f"File: {OUT_FILE} ({size_mb:.2f} MB)")
    if size_mb > MAX_SIZE_MB:
        print(f"WARNING: the file is larger than {MAX_SIZE_MB} MB. "
              "Set MIN_COUNT = 0.5 or 1 at the top of this script to shrink it.")


if __name__ == "__main__":
    main()