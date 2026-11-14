"""
b_aggregate.py
Aggregates raw NASA FIRMS fire detections (MODIS and VIIRS) into weekly counts
per 0.25 degree grid cell.

Run from the project root:
    python scripts/b_aggregate.py

Input : data/raw/modis/*.csv and data/raw/viirs/*.csv
Output: data/processed/weekly_counts.csv
        columns: cell_lat, cell_lon, week_start, sensor, count, frp_sum
"""

import glob
import os

import numpy as np
import pandas as pd

# ---------- Configuration ----------
RAW_DIRS = {
    "modis": os.path.join("data", "raw", "modis"),
    "viirs": os.path.join("data", "raw", "viirs"),
}
OUT_DIR = os.path.join("data", "processed")
OUT_FILE = os.path.join(OUT_DIR, "weekly_counts.csv")

CHUNK_SIZE = 500_000          # rows per chunk
CELL_SIZE = 0.25              # grid size in degrees
MODIS_MIN_CONFIDENCE = 30     # keep MODIS confidence >= 30
VIIRS_KEEP = ["n", "h"]       # keep VIIRS nominal and high, drop low

# Columns we need from the raw files ("type" is added only if present)
BASE_COLS = ["latitude", "longitude", "acq_date", "confidence", "frp"]
GROUP_COLS = ["cell_lat", "cell_lon", "week_start", "sensor"]


def process_chunk(chunk, sensor):
    """
    Filters one chunk and returns a grouped DataFrame with columns
    cell_lat, cell_lon, week_start, sensor, count, frp_sum.
    Also returns the number of rows kept after filtering.
    """
    # Make sure numeric columns are numeric (bad values become NaN)
    chunk["latitude"] = pd.to_numeric(chunk["latitude"], errors="coerce")
    chunk["longitude"] = pd.to_numeric(chunk["longitude"], errors="coerce")
    chunk["frp"] = pd.to_numeric(chunk["frp"], errors="coerce").fillna(0.0)

    # Step 3: if a "type" column exists, keep only type == 0
    # (archive files have it, NRT files do not)
    if "type" in chunk.columns:
        chunk = chunk[pd.to_numeric(chunk["type"], errors="coerce") == 0]

    # Step 4: confidence filter, different for each sensor
    if sensor == "modis":
        # Numeric confidence 0-100; rows that fail conversion become NaN and are dropped
        conf = pd.to_numeric(chunk["confidence"], errors="coerce")
        chunk = chunk[conf >= MODIS_MIN_CONFIDENCE]
    else:
        # VIIRS letters l / n / h; lowercase and strip first
        conf = chunk["confidence"].astype(str).str.strip().str.lower()
        chunk = chunk[conf.isin(VIIRS_KEEP)]

    # Drop rows with missing coordinates and parse dates
    chunk = chunk.dropna(subset=["latitude", "longitude"])
    dates = pd.to_datetime(chunk["acq_date"], errors="coerce")
    valid = dates.notna()
    chunk = chunk[valid]
    dates = dates[valid]

    if len(chunk) == 0:
        return None, 0

    # Step 5: grid cell centers
    cell_lat = np.floor(chunk["latitude"].to_numpy() / CELL_SIZE) * CELL_SIZE + CELL_SIZE / 2
    cell_lon = np.floor(chunk["longitude"].to_numpy() / CELL_SIZE) * CELL_SIZE + CELL_SIZE / 2

    # Step 6: week_start = Monday of that week (weekday: Monday=0 ... Sunday=6)
    monday = dates.dt.normalize() - pd.to_timedelta(dates.dt.weekday, unit="D")

    out = pd.DataFrame({
        "cell_lat": np.round(cell_lat, 3),
        "cell_lon": np.round(cell_lon, 3),
        "week_start": monday.dt.strftime("%Y-%m-%d").to_numpy(),
        "sensor": sensor,
        "frp": chunk["frp"].to_numpy(),
    })

    # Step 7: group inside the chunk (count rows and sum frp)
    grouped = out.groupby(GROUP_COLS, as_index=False).agg(
        count=("frp", "size"),
        frp_sum=("frp", "sum"),
    )
    return grouped, len(out)


def process_file(path, sensor):
    """
    Reads one CSV in chunks. Returns (list of grouped chunks, rows read, rows kept).
    Each file is handled separately because the columns can differ
    (the NRT file has no "type" column).
    """
    # Read only the header to see which columns exist
    header = pd.read_csv(path, nrows=0).columns.tolist()

    missing = [c for c in BASE_COLS if c not in header]
    if missing:
        print(f"  WARNING: {os.path.basename(path)} is missing columns {missing}, skipped.")
        return [], 0, 0

    # Step 2: keep only needed columns; "type" only if it exists
    usecols = BASE_COLS + (["type"] if "type" in header else [])

    parts = []
    rows_read = 0
    rows_kept = 0

    # confidence is read as string so VIIRS letters are not damaged
    reader = pd.read_csv(
        path,
        usecols=usecols,
        dtype={"confidence": str},
        chunksize=CHUNK_SIZE,
    )
    for chunk in reader:
        rows_read += len(chunk)
        grouped, kept = process_chunk(chunk, sensor)
        if grouped is not None:
            parts.append(grouped)
            rows_kept += kept

    return parts, rows_read, rows_kept


def main():
    # Step 1: make sure the output folder exists
    os.makedirs(OUT_DIR, exist_ok=True)

    all_parts = []                 # grouped chunks from all files and sensors
    total_read = 0
    kept_per_sensor = {"modis": 0, "viirs": 0}

    for sensor, folder in RAW_DIRS.items():
        files = sorted(glob.glob(os.path.join(folder, "*.csv")))

        # If a folder has no CSV files, say so and continue with the other sensor
        if not files:
            print(f"No CSV files found in {folder}. Skipping {sensor}.")
            continue

        for path in files:
            print(f"Reading {path} ...")
            parts, rows_read, rows_kept = process_file(path, sensor)
            all_parts.extend(parts)
            total_read += rows_read
            kept_per_sensor[sensor] += rows_kept
            print(f"  rows read: {rows_read:,}   rows kept: {rows_kept:,}")

    if not all_parts:
        print("No data was aggregated. Nothing written.")
        return

    # Step 7 (final): the same cell-week can appear in several chunks or files,
    # so concatenate everything and group again, summing the values
    result = pd.concat(all_parts, ignore_index=True)
    result = result.groupby(GROUP_COLS, as_index=False).agg(
        count=("count", "sum"),
        frp_sum=("frp_sum", "sum"),
    )
    result["count"] = result["count"].astype(int)
    result["frp_sum"] = result["frp_sum"].round(3)

    # Step 8: sort and save
    result = result.sort_values(["week_start", "sensor", "cell_lat", "cell_lon"])
    result = result[["cell_lat", "cell_lon", "week_start", "sensor", "count", "frp_sum"]]
    result.to_csv(OUT_FILE, index=False)

    # Step 9: summary
    print("\n===== Summary =====")
    print(f"Raw rows read: {total_read:,}")
    for sensor in RAW_DIRS:
        print(f"Rows kept ({sensor}): {kept_per_sensor[sensor]:,}")
    for sensor in RAW_DIRS:
        sub = result[result["sensor"] == sensor]
        if len(sub) > 0:
            print(f"week_start range ({sensor}): {sub['week_start'].min()} to {sub['week_start'].max()}")
        else:
            print(f"week_start range ({sensor}): no data")
    size_mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f"Output rows: {len(result):,}")
    print(f"Output file: {OUT_FILE} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()