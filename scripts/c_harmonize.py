"""
c_harmonize.py
Computes week-of-year scaling factors that make the MODIS series comparable to
VIIRS, saves them to JSON, builds the harmonized regional series and plots a check.

Run from the project root:
    python scripts/c_harmonize.py

Input : data/processed/weekly_counts.csv
Output: data/processed/harmonization.json
        outputs/harmonization_check.png
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt

# ---------- Configuration ----------
IN_FILE = os.path.join("data", "processed", "weekly_counts.csv")
OUT_JSON = os.path.join("data", "processed", "harmonization.json")
OUT_PNG = os.path.join("outputs", "harmonization_check.png")

VIIRS_START_WEEK = pd.Timestamp("2012-03-05")  # first week that uses VIIRS
MIN_WEEKS_PER_FACTOR = 3                       # fewer overlap weeks -> use overall ratio
FACTOR_MIN, FACTOR_MAX = 0.2, 20.0             # clip range for the final factors


def load_regional_totals():
    """Step 1: regional weekly totals per sensor (sum over ALL cells)."""
    df = pd.read_csv(IN_FILE)
    df["week_start"] = pd.to_datetime(df["week_start"])

    # Sum counts per week and sensor, then put sensors in columns (missing = 0)
    totals = (df.groupby(["week_start", "sensor"])["count"].sum()
                .unstack("sensor", fill_value=0))
    for sensor in ("modis", "viirs"):
        if sensor not in totals.columns:
            totals[sensor] = 0
    totals = totals[["modis", "viirs"]].rename(
        columns={"modis": "modis_total", "viirs": "viirs_total"})
    totals = totals.sort_index().reset_index()  # columns: week_start, modis_total, viirs_total
    return totals


def compute_factors(totals):
    """
    Steps 2-4: overlap period and the 53 smoothed week-of-year factors.
    Returns (factors dict {1..53: float}, overlap_end, overall_ratio, table DataFrame).
    """
    # Last week with data for each sensor (final week may be partial -> excluded)
    modis_last = totals.loc[totals["modis_total"] > 0, "week_start"].max()
    viirs_last = totals.loc[totals["viirs_total"] > 0, "week_start"].max()

    # Step 2: overlap weeks = from VIIRS start, both sensors have data,
    # excluding the final week of each sensor
    mask = ((totals["week_start"] >= VIIRS_START_WEEK)
            & (totals["week_start"] < modis_last)
            & (totals["week_start"] < viirs_last)
            & (totals["modis_total"] > 0)
            & (totals["viirs_total"] > 0))
    overlap = totals[mask].copy()
    if overlap.empty:
        sys.exit("ERROR: no overlap weeks between MODIS and VIIRS found.")
    overlap_end = overlap["week_start"].max()
    overlap["woy"] = overlap["week_start"].dt.isocalendar().week.astype(int)

    # Overall ratio over the whole overlap (fallback value)
    overall_ratio = overlap["viirs_total"].sum() / overlap["modis_total"].sum()

    # Step 3: factor per ISO week of year
    rows = []
    for w in range(1, 54):
        sub = overlap[overlap["woy"] == w]
        n = len(sub)
        modis_sum = sub["modis_total"].sum()
        if n < MIN_WEEKS_PER_FACTOR or modis_sum == 0:
            raw = overall_ratio
            used_fallback = True
        else:
            raw = sub["viirs_total"].sum() / modis_sum
            used_fallback = False
        rows.append({"week": w, "n_overlap_weeks": n,
                     "raw_factor": raw, "fallback": used_fallback})
    table = pd.DataFrame(rows)

    # Step 4: circular 3-point moving average (week 1 neighbours week 53), then clip
    raw_arr = table["raw_factor"].to_numpy()
    smooth = (np.roll(raw_arr, 1) + raw_arr + np.roll(raw_arr, -1)) / 3.0
    smooth = np.clip(smooth, FACTOR_MIN, FACTOR_MAX)
    table["final_factor"] = smooth

    factors = {int(w): float(f) for w, f in zip(table["week"], smooth)}
    return factors, overlap_end, overall_ratio, table, viirs_last


def save_json(factors, overlap_end):
    """Step 5: write harmonization.json."""
    out = {
        "method": "ratio of VIIRS to MODIS weekly totals per ISO week-of-year, overlap period only",
        "overlap_start": VIIRS_START_WEEK.strftime("%Y-%m-%d"),
        "overlap_end": overlap_end.strftime("%Y-%m-%d"),
        "factor_by_week_of_year": {str(w): round(f, 4) for w, f in factors.items()},
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2)


def build_harmonized(totals, factors, viirs_last):
    """
    Step 6: harmonized regional series.
    - before 2012-03-05: modis_total * factor[ISO week]
    - from 2012-03-05:   viirs_total
    Drops the first week of the data and the last (partial) VIIRS week.
    """
    h = totals.copy()
    h["woy"] = h["week_start"].dt.isocalendar().week.astype(int)
    h["factor"] = h["woy"].map(factors)

    is_viirs = h["week_start"] >= VIIRS_START_WEEK
    h["harmonized"] = np.where(is_viirs, h["viirs_total"],
                               h["modis_total"] * h["factor"])
    h["source"] = np.where(is_viirs, "viirs", "modis_scaled")

    # Drop the very first week (partial) and the last VIIRS week (partial);
    # anything after it has no VIIRS data, so it is dropped as well
    first_week = h["week_start"].min()
    h = h[(h["week_start"] > first_week) & (h["week_start"] < viirs_last)]
    return h.reset_index(drop=True)


def plot_check(totals, harmonized):
    """Step 7: two stacked panels sharing the x axis."""
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # TOP: raw totals show the mismatch between sensors
    ax1.plot(totals["week_start"], totals["modis_total"],
             color="tab:blue", linewidth=1, label="MODIS (raw)")
    ax1.plot(totals["week_start"], totals["viirs_total"],
             color="tab:red", linewidth=1, label="VIIRS (raw)")
    ax1.set_title("Raw weekly fire detections (all cells)")
    ax1.set_ylabel("Weekly fire count")
    ax1.legend(loc="upper left")

    # BOTTOM: harmonized series, split by source for clarity
    before = harmonized[harmonized["week_start"] < VIIRS_START_WEEK]
    after = harmonized[harmonized["week_start"] >= VIIRS_START_WEEK]
    ax2.plot(before["week_start"], before["harmonized"],
             color="tab:blue", linewidth=1, label="MODIS scaled to VIIRS level")
    ax2.plot(after["week_start"], after["harmonized"],
             color="tab:red", linewidth=1, label="VIIRS")
    ax2.axvline(VIIRS_START_WEEK, color="black", linestyle="--", linewidth=1,
                label="VIIRS start (2012-03-05)")
    ax2.set_title("Harmonized weekly series")
    ax2.set_xlabel("Week start")
    ax2.set_ylabel("Harmonized fire count")
    ax2.legend(loc="upper left")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)


def main():
    if not os.path.exists(IN_FILE):
        sys.exit(f"ERROR: {IN_FILE} not found. Run scripts/b_aggregate.py first.")

    totals = load_regional_totals()
    factors, overlap_end, overall_ratio, table, viirs_last = compute_factors(totals)
    save_json(factors, overlap_end)

    harmonized = build_harmonized(totals, factors, viirs_last)
    plot_check(totals, harmonized)

    # Step 8: print the factor table and the overall ratio
    print("Factor table (week of year, overlap weeks, raw factor, final smoothed factor):")
    printable = table.copy()
    printable["raw_factor"] = printable["raw_factor"].round(3)
    printable["final_factor"] = printable["final_factor"].round(3)
    print(printable.to_string(index=False))
    print(f"\nOverall VIIRS/MODIS ratio over the overlap: {overall_ratio:.4f}")
    print(f"Overlap period: {VIIRS_START_WEEK.date()} to {overlap_end.date()}")
    print(f"Harmonized series: {len(harmonized)} weeks "
          f"({harmonized['week_start'].min().date()} to {harmonized['week_start'].max().date()})")
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()