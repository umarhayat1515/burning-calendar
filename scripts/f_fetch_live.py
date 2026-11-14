"""
f_fetch_live.py
Downloads near-real-time VIIRS hotspots from the NASA FIRMS Area API and
saves them as a small JSON file for the website.

Run from the project root:
    python scripts/f_fetch_live.py

Needs the environment variable FIRMS_MAP_KEY (or a line FIRMS_MAP_KEY=... in .env).
Output: docs/data/live_hotspots.json
"""

import datetime
import io
import json
import os
import sys

import pandas as pd
import requests

# ---------- Configuration ----------
KEY_NAME = "FIRMS_MAP_KEY"
SOURCE = "VIIRS_NOAA20_NRT"
SOURCE_LABEL = "VIIRS NOAA-20 NRT"
WEST, SOUTH, EAST, NORTH = 60, 23, 78, 37
DAY_RANGE = 5
TIMEOUT_SECONDS = 60
OUT_FILE = os.path.join("docs", "data", "live_hotspots.json")
ENV_FILE = ".env"

REQUIRED_COLS = ["latitude", "longitude", "acq_date", "acq_time", "frp", "confidence"]


def read_env_file(path):
    """Parses a simple .env file (KEY=VALUE lines) by hand. Returns a dict."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, value = line.partition("=")
            # Remove optional surrounding quotes
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_map_key():
    """Step 1: environment variable first, then the .env file."""
    key = os.environ.get(KEY_NAME, "").strip()
    if not key:
        key = read_env_file(ENV_FILE).get(KEY_NAME, "").strip()
    if not key:
        print(f"ERROR: {KEY_NAME} is not set. Set it as an environment variable "
              f"or add the line {KEY_NAME}=your_key to the file {ENV_FILE} in the project root.")
        sys.exit(1)
    return key


def fail(message, key):
    """Prints a message (with the key hidden) and exits with a non-zero code."""
    print(message.replace(key, "***"))
    sys.exit(1)


def fetch_csv(key):
    """Step 2: calls the FIRMS Area API and returns the CSV text."""
    url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{SOURCE}/"
           f"{WEST},{SOUTH},{EAST},{NORTH}/{DAY_RANGE}")
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # The exception text can contain the URL (and therefore the key), so hide it
        fail(f"ERROR: request failed: {type(exc).__name__}: {exc}", key)

    text = response.text

    # HTTP error status
    if response.status_code != 200:
        print(f"ERROR: HTTP status {response.status_code}. First 300 characters of the response:")
        fail(text[:300], key)

    # The response must be CSV: the first line must be a header containing "latitude"
    lines = text.strip().splitlines()
    if not lines or "latitude" not in lines[0].lower():
        print("ERROR: the response is not CSV. First 300 characters of the response:")
        fail(text[:300], key)

    return text


def main():
    key = get_map_key()
    text = fetch_csv(key)

    # Step 3: parse the CSV (confidence and times stay strings)
    df = pd.read_csv(io.StringIO(text), dtype={"confidence": str, "acq_time": str, "acq_date": str})

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        print(f"ERROR: the response is missing columns: {missing}")
        sys.exit(1)

    points = []
    if len(df) > 0:
        # Keep only nominal and high confidence (lowercase letters first)
        conf = df["confidence"].astype(str).str.strip().str.lower()
        df = df[conf.isin(["n", "h"])].copy()

        # Clean numeric columns
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0.0)
        df = df.dropna(subset=["latitude", "longitude", "acq_date", "acq_time"])

        # Step 4: acq_time as a 4-character zero-padded string (205 -> "0205")
        df["acq_time"] = df["acq_time"].astype(str).str.strip().str.zfill(4)

        df = df.sort_values(["acq_date", "acq_time"])

        # Step 5: build the points list with rounded numbers
        for lat, lon, date, time, frp in zip(df["latitude"], df["longitude"],
                                             df["acq_date"], df["acq_time"], df["frp"]):
            points.append([round(float(lat), 4), round(float(lon), 4),
                           str(date), str(time), round(float(frp), 1)])

    # Save the file (also when the points list is empty)
    out = {
        "fetched_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE_LABEL,
        "days": DAY_RANGE,
        "points": points,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))

    # Step 6: summary
    print(f"Points: {len(points):,}")
    if points:
        latest = max(points, key=lambda p: (p[2], p[3]))  # latest date, then time
        print(f"Latest detection: {latest[2]} {latest[3]} UTC")
    else:
        print("No detections in the last "
              f"{DAY_RANGE} days (empty points list written).")
    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()