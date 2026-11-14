/**
 * main.js
 * Page controller for the Burning Activity Calendar.
 * Loads the data, sets up the map and redraws all charts when the user
 * draws, edits or deletes an area of interest (AOI) rectangle.
 */

// ---------- Shared state ----------
var fireData = null;      // historical fire data (from fire_data.json)
var live = null;          // live hotspot data (from live_hotspots.json), or null
var lastBounds = null;    // most recent AOI bounds, or null if no AOI
var readyMessage = "";    // status text shown when data is loaded and no AOI is drawn

// IDs of the three chart containers
var CHART_IDS = ["calendar-chart", "climatology-chart", "anomaly-chart"];

// CSS classes that can be set on #warning
var WARNING_CLASSES = ["warn-normal", "warn-elevated", "warn-high", "warn-nodata"];

// ---------- Small DOM helpers ----------

/** Sets the plain text of an element by id (safe against HTML injection). */
function setText(id, text) {
  var el = document.getElementById(id);
  if (el) el.textContent = text;
}

/** Sets the HTML of an element by id. Only use with escaped content. */
function setHtml(id, html) {
  var el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

/** Escapes a value so it can be placed safely inside HTML. */
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Removes the warning text and all warning classes from #warning. */
function clearWarning() {
  var el = document.getElementById("warning");
  if (!el) return;
  el.textContent = "";
  WARNING_CLASSES.forEach(function (cls) { el.classList.remove(cls); });
}

/** Removes all three charts from the page. */
function clearCharts() {
  CHART_IDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) Plotly.purge(el);
  });
}

// ---------- ISO week -> approximate month ----------

var MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Converts an ISO week number (1..53) to an approximate label such as
 * "late Oct" or "mid Nov". Uses the middle of the week in a non-leap year.
 */
function weekToMonthLabel(week) {
  var w = Math.min(Math.max(Math.round(week), 1), 53);
  // Day of year at the middle of the week (week 1 is centred near day 4)
  var dayOfYear = (w - 1) * 7 + 4;
  // Use a fixed non-leap year; day 0 is Jan 1
  var date = new Date(Date.UTC(2023, 0, 1 + dayOfYear - 1));
  var month = date.getUTCMonth();
  var day = date.getUTCDate();
  var part = day <= 10 ? "early" : (day <= 20 ? "mid" : "late");
  return part + " " + MONTH_NAMES[month];
}

// ---------- Live data ----------

/**
 * Builds the text for #live-status from the live data file.
 * Returns plain text (set with textContent).
 */
function buildLiveStatus(liveData) {
  var points = liveData.points;
  var n = points.length;

  // Find the most recent detection (compare "YYYY-MM-DD" + "HHMM" strings)
  var latest = points[0];
  points.forEach(function (p) {
    if ((p[2] + p[3]) > (latest[2] + latest[3])) latest = p;
  });

  // "2026-11-15T01:00:00Z" -> "2026-11-15 01:00"
  var updated = String(liveData.fetched_utc || "")
    .replace("T", " ")
    .slice(0, 16);

  var text = "Live layer (near real time): " + n + " detections in the last " +
    liveData.days + " days. Latest detection " + latest[2] + " " + latest[3] +
    " UTC. File updated " + updated + " UTC.";
  if (liveData.source) text += " Source: " + liveData.source + ".";
  return text;
}

/** Shows the live layer on the map and fills #live-status. */
function applyLiveData() {
  if (live && live.points && live.points.length > 0) {
    showLivePoints(live.points);
    setText("live-status", buildLiveStatus(live));
  } else {
    // File loaded but has no detections, or file missing
    if (live && live.points) showLivePoints([]);
    setText("live-status", "Live layer not available.");
  }
}

// ---------- AOI handling ----------

/**
 * Called by the map when the user draws/edits (bounds) or deletes (null) a rectangle.
 * @param {{south:number, west:number, north:number, east:number}|null} bounds
 */
function onAOIChange(bounds) {
  lastBounds = bounds;

  // Rectangle deleted: reset everything back to the "ready" state
  if (bounds === null) {
    setHtml("summary", "");
    clearWarning();
    setText("status", readyMessage);
    clearCharts();
    return;
  }

  // Data not loaded yet: the AOI is remembered and redrawn once data arrives
  if (!fireData) {
    setText("status", "Data is still loading, please wait...");
    return;
  }

  try {
    // Compute everything we need from the AOI
    var series = getAOISeries(fireData, bounds);

    // No data cells inside the AOI
    if (!series || series.cellCount === 0) {
      setText("status", "No fire data in this area");
      setHtml("summary", "");
      clearCharts();
      clearWarning();
      return;
    }

    var clim = getClimatology(series);
    var anomalies = getAnomalies(series, clim);
    var critical = getCriticalWeeks(series, clim, 5);
    var matrix = getCalendarMatrix(series);
    var peak = getPeakSeason(clim);

    // Draw the three charts
    drawCalendarHeatmap("calendar-chart", matrix);
    drawClimatology("climatology-chart", clim, peak);
    drawAnomalies("anomaly-chart", anomalies);

    // Restore the normal status line
    setText("status", readyMessage);

    // Fill the summary panel
    setHtml("summary", buildSummaryHtml(series, peak, critical));

    // Early warning from live data (if available)
    if (live) {
      var liveAOI = getLiveInAOI(live, bounds);
      var warn = getEarlyWarning(clim, live, liveAOI);
      var warnEl = document.getElementById("warning");
      if (warnEl) {
        WARNING_CLASSES.forEach(function (cls) { warnEl.classList.remove(cls); });
        warnEl.textContent = warn.message;
        warnEl.classList.add("warn-" + warn.level);
      }
    } else {
      clearWarning();
    }
  } catch (err) {
    console.error(err);
    setText("status", "Error while analysing this area: " + err.message);
  }
}

/**
 * Builds the HTML for the #summary panel.
 * @param {{cellCount:number}} series
 * @param {{startWeek:number, endWeek:number, peakWeek:number}} peak
 * @param {Array<{week:string, value:number, zscore:number}>} critical
 */
function buildSummaryHtml(series, peak, critical) {
  var html = "";

  // Number of 0.25 degree grid cells covered by the AOI
  html += "<p><strong>Area covered:</strong> " + series.cellCount +
          " cells (0.25&deg; grid)</p>";

  // Peak season as week numbers and approximate months
  html += "<p><strong>Peak season:</strong> weeks " + peak.startWeek +
          " to " + peak.endWeek + ", approx. " +
          weekToMonthLabel(peak.startWeek) + " to " +
          weekToMonthLabel(peak.endWeek) + "</p>";

  // Top critical weeks as an ordered list
  html += "<p><strong>Top 5 critical weeks:</strong></p>";
  if (critical && critical.length > 0) {
    html += "<ol>";
    critical.forEach(function (c) {
      html += "<li>" + escapeHtml(c.week) +
              ": value " + Number(c.value).toFixed(1) +
              ", z-score " + Number(c.zscore).toFixed(1) + "</li>";
    });
    html += "</ol>";
  } else {
    html += "<p>No critical weeks found.</p>";
  }

  return html;
}

// ---------- Startup ----------

document.addEventListener("DOMContentLoaded", function () {
  // 1. Load the historical fire data
  setText("status", "Loading data...");
  loadFireData("data/fire_data.json")
    .then(function (d) {
      fireData = d;
      readyMessage = "Data ready (" + d.meta.start + " to " + d.meta.end +
                     "). Draw a rectangle on the map.";
      setText("status", readyMessage);

      // If the user already drew an AOI while data was loading, process it now
      if (lastBounds) onAOIChange(lastBounds);
    })
    .catch(function (err) {
      console.error(err);
      setText("status", "Error: could not load data/fire_data.json (" +
                        err.message + ").");
    });

  // 2. Set up the map (calls onAOIChange when the rectangle changes)
  initMap("map", onAOIChange);

  // 3. Load the live hotspot layer (optional; page works without it)
  Promise.resolve(loadLiveData("data/live_hotspots.json"))
    .catch(function (err) {
      console.error(err);
      return null;
    })
    .then(function (l) {
      live = l;
      applyLiveData();

      // If an AOI already exists, refresh so the early warning appears
      if (lastBounds && fireData) onAOIChange(lastBounds);
    });
});