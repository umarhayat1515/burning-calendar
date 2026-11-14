#!/usr/bin/env python3
"""
e_make_mock.py
Generate FAKE fire data for the Burning Activity Calendar and write
docs/data/fire_data.json in the exact format of the project spec.

Run from the project root:
    python scripts/e_make_mock.py
"""

import json
import datetime as dt
import numpy as np

OUT_PATH = "docs/data/fire_data.json"

GRID = 0.25
LAT_MIN, LAT_MAX = 29.0, 33.0
LON_MIN, LON_MAX = 72.0, 77.0
START = dt.date(2000, 11, 6)    # a Monday
END = dt.date(2024, 12, 30)     # a Monday
VIIRS_START = "2012-03-05"

BASE = 8.0
NOISE_SIGMA = 0.5
N_ANOMALIES = 6
ANOMALY_FACTOR = 3.0


def gauss(x, mu, sigma):
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def seasonality(woy):
    """Strong peak ISO weeks 43-46, smaller peak weeks 16-20, near zero otherwise."""
    woy = np.asarray(woy, dtype=float)
    autumn = 1.0 * gauss(woy, 44.5, 1.8)
    spring = 0.3 * gauss(woy, 18.0, 1.6)
    baseline = 0.01
    return baseline + autumn + spring


def main():
    np.random.seed(42)

    # ---- weeks: every Monday, continuous ----
    weeks = []
    d = START
    while d <= END:
        weeks.append(d)
        d += dt.timedelta(days=7)
    n_weeks = len(weeks)
    week_strs = [w.isoformat() for w in weeks]
    week_woy = np.array([w.isocalendar()[1] for w in weeks])
    week_year = np.array([w.year for w in weeks])

    # ---- cells: centers on the 0.25 degree grid ----
    n_lat = int(round((LAT_MAX - LAT_MIN) / GRID))
    n_lon = int(round((LON_MAX - LON_MIN) / GRID))
    cells = []
    for i in range(n_lat):
        for j in range(n_lon):
            lat = LAT_MIN + i * GRID + GRID / 2.0   # 29.125 ... 32.875
            lon = LON_MIN + j * GRID + GRID / 2.0   # 72.125 ... 76.875
            cells.append((lat, lon))
    n_cells = len(cells)
    cell_lat = np.array([c[0] for c in cells])
    cell_lon = np.array([c[1] for c in cells])

    # ---- cell weights: random 0..1, x3 inside the core region ----
    cell_weight = np.random.uniform(0.0, 1.0, size=n_cells)
    core = (cell_lat >= 30.0) & (cell_lat <= 32.0) & (cell_lon >= 73.5) & (cell_lon <= 76.0)
    cell_weight = np.where(core, cell_weight * 3.0, cell_weight)

    # ---- seasonality per week ----
    season = seasonality(week_woy)

    # ---- anomalous weeks: 6 weeks in 6 different years, counts 3x ----
    anomaly_mult = np.ones(n_weeks)
    years = np.array(sorted(set(week_year.tolist())))
    chosen_years = np.random.choice(years, size=N_ANOMALIES, replace=False)
    anomaly_weeks = []
    for y in chosen_years:
        candidates = np.where((week_year == y) & (season > 0.2))[0]
        if len(candidates) == 0:
            candidates = np.where(week_year == y)[0]
        idx = int(np.random.choice(candidates))
        anomaly_mult[idx] = ANOMALY_FACTOR
        anomaly_weeks.append(week_strs[idx])

    # ---- counts = base x seasonality x cell weight x noise (x anomaly) ----
    noise = np.random.lognormal(mean=0.0, sigma=NOISE_SIGMA, size=(n_weeks, n_cells))
    counts = (BASE
              * season[:, None]
              * cell_weight[None, :]
              * noise
              * anomaly_mult[:, None])
    counts = np.round(counts, 1)

    # ---- sparse records: only count > 0 ----
    w_idx, c_idx = np.nonzero(counts > 0)
    order = np.lexsort((w_idx, c_idx))   # sort by cell, then week
    w_idx = w_idx[order]
    c_idx = c_idx[order]
    vals = counts[w_idx, c_idx]
    records = [[int(c), int(w), float(v)] for c, w, v in zip(c_idx, w_idx, vals)]

    out = {
        "meta": {
            "grid": GRID,
            "start": week_strs[0],
            "end": week_strs[-1],
            "viirs_start": VIIRS_START,
        },
        "weeks": week_strs,
        "cells": [[float(a), float(b)] for a, b in cells],
        "records": records,
    }

    text = json.dumps(out, separators=(",", ":"))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)

    size_mb = len(text.encode("utf-8")) / (1024.0 * 1024.0)
    print("weeks:   ", n_weeks)
    print("cells:   ", n_cells)
    print("records: ", len(records))
    print("anomalous weeks (3x):", ", ".join(sorted(anomaly_weeks)))
    print("file size: %.2f MB -> %s" % (size_mb, OUT_PATH))


if __name__ == "__main__":
    main()