#!/usr/bin/env python3
"""
e_make_mock_live.py
Generate FAKE live hotspot data for the Burning Activity Calendar and write
docs/data/live_hotspots.json in the exact format of the project spec.

Run from the project root:
    python scripts/e_make_mock_live.py
"""

import json
import datetime as dt
import numpy as np

OUT_PATH = "docs/data/live_hotspots.json"

N_POINTS = 900
SEED = 7
DAYS = 5
CLUSTER_FRACTION = 0.70

# Punjab cluster box (gaussian centered here, clipped to the box)
CL_LAT_MIN, CL_LAT_MAX = 30.0, 32.0
CL_LON_MIN, CL_LON_MAX = 73.5, 76.0

# Whole mock region (uniform background)
LAT_MIN, LAT_MAX = 29.0, 33.0
LON_MIN, LON_MAX = 72.0, 77.0


def main():
    rng = np.random.RandomState(SEED)

    now = dt.datetime.now(dt.timezone.utc)
    fetched_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.date()
    dates = [(today - dt.timedelta(days=k)).isoformat() for k in range(DAYS)]

    n_cluster = int(round(N_POINTS * CLUSTER_FRACTION))
    n_uniform = N_POINTS - n_cluster

    # clustered points: gaussian around the center of the Punjab box,
    # sigma = a quarter of the box size, clipped to the box
    c_lat = (CL_LAT_MIN + CL_LAT_MAX) / 2.0
    c_lon = (CL_LON_MIN + CL_LON_MAX) / 2.0
    s_lat = (CL_LAT_MAX - CL_LAT_MIN) / 4.0
    s_lon = (CL_LON_MAX - CL_LON_MIN) / 4.0
    lat_c = np.clip(rng.normal(c_lat, s_lat, n_cluster), CL_LAT_MIN, CL_LAT_MAX)
    lon_c = np.clip(rng.normal(c_lon, s_lon, n_cluster), CL_LON_MIN, CL_LON_MAX)

    # uniform points over the whole region
    lat_u = rng.uniform(LAT_MIN, LAT_MAX, n_uniform)
    lon_u = rng.uniform(LON_MIN, LON_MAX, n_uniform)

    lats = np.concatenate([lat_c, lat_u])
    lons = np.concatenate([lon_c, lon_u])

    # shuffle so clustered and uniform points are mixed
    order = rng.permutation(N_POINTS)
    lats = lats[order]
    lons = lons[order]

    date_idx = rng.randint(0, DAYS, N_POINTS)
    hours = rng.randint(0, 24, N_POINTS)
    minutes = rng.randint(0, 60, N_POINTS)
    frps = np.round(rng.lognormal(mean=1.8, sigma=0.8, size=N_POINTS), 1)

    points = []
    for i in range(N_POINTS):
        acq_date = dates[int(date_idx[i])]
        acq_time = "%02d%02d" % (int(hours[i]), int(minutes[i]))
        points.append([
            round(float(lats[i]), 4),
            round(float(lons[i]), 4),
            acq_date,
            acq_time,
            float(frps[i]),
        ])

    out = {
        "fetched_utc": fetched_utc,
        "source": "VIIRS S-NPP NRT (MOCK)",
        "days": DAYS,
        "points": points,
    }

    text = json.dumps(out, separators=(",", ":"))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    latest = max(points, key=lambda p: (p[2], p[3]))
    print("points: ", len(points))
    print("latest acq_date: %s  acq_time: %s" % (latest[2], latest[3]))
    print("written to", OUT_PATH)


if __name__ == "__main__":
    main()