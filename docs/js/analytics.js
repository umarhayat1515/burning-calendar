// docs/js/analytics.js
// Global plain-JS functions (no imports). Only the four functions below are defined here.

/**
 * Return the ISO week number (1..53) for a date string "YYYY-MM-DD".
 * Uses UTC dates throughout to avoid timezone bugs.
 */
function isoWeek(dateString) {
  var parts = dateString.split("-");
  var y = parseInt(parts[0], 10);
  var m = parseInt(parts[1], 10);
  var d = parseInt(parts[2], 10);
  var date = new Date(Date.UTC(y, m - 1, d));

  // ISO weeks are anchored on Thursday: move to the Thursday of this week.
  // getUTCDay(): Sunday=0 ... Saturday=6; ISO treats Sunday as day 7.
  var dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);

  // Week number = how many whole weeks since Jan 1 of that Thursday's year.
  var yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
}

/**
 * Fetch the fire data JSON and return the parsed object (a Promise).
 * Throws an Error if the HTTP response is not ok.
 */
function loadFireData(url) {
  return fetch(url).then(function (response) {
    if (!response.ok) {
      throw new Error("Failed to load " + url + " (HTTP " + response.status + ")");
    }
    return response.json();
  });
}

/**
 * Build the weekly series for the area of interest (AOI).
 * A cell is included if its center lies inside bounds
 * (south <= lat <= north and west <= lon <= east).
 * Returns {weeks, values, cellCount}, with values aligned to data.weeks
 * (zero where there are no records).
 */
function getAOISeries(data, bounds) {
  // Step 1: collect the indices of all cells whose center is inside the AOI.
  var included = new Set();
  for (var i = 0; i < data.cells.length; i++) {
    var lat = data.cells[i][0];
    var lon = data.cells[i][1];
    if (lat >= bounds.south && lat <= bounds.north &&
        lon >= bounds.west && lon <= bounds.east) {
      included.add(i);
    }
  }

  // Step 2: one pass over the sparse records, summing counts per week.
  var values = new Array(data.weeks.length).fill(0);
  for (var r = 0; r < data.records.length; r++) {
    var rec = data.records[r]; // [cell_index, week_index, harmonized_count]
    if (included.has(rec[0])) {
      values[rec[1]] += rec[2];
    }
  }

  return { weeks: data.weeks, values: values, cellCount: included.size };
}

/**
 * Climatology: mean and population standard deviation of the weekly values,
 * grouped by ISO week of year (1..53). A week of year with no data gets 0.
 * Returns {weekOfYear: [1..53], mean: [...], std: [...]}.
 */
function getClimatology(series) {
  // Accumulate values per week of year (index 0 = week 1, ..., index 52 = week 53).
  var groups = [];
  for (var w = 0; w < 53; w++) groups.push([]);

  for (var i = 0; i < series.weeks.length; i++) {
    var woy = isoWeek(series.weeks[i]); // 1..53
    groups[woy - 1].push(series.values[i]);
  }

  var weekOfYear = [];
  var mean = [];
  var std = [];

  for (var k = 0; k < 53; k++) {
    var vals = groups[k];
    weekOfYear.push(k + 1);

    if (vals.length === 0) {
      // No data for this week of year.
      mean.push(0);
      std.push(0);
      continue;
    }

    var sum = 0;
    for (var a = 0; a < vals.length; a++) sum += vals[a];
    var mu = sum / vals.length;

    // Population standard deviation (divide by N, not N-1).
    var sq = 0;
    for (var b = 0; b < vals.length; b++) sq += (vals[b] - mu) * (vals[b] - mu);

    mean.push(mu);
    std.push(Math.sqrt(sq / vals.length));
  }

  return { weekOfYear: weekOfYear, mean: mean, std: std };
}

// ---------------------------------------------------------------------------
// Test block (paste into the browser console on the page, or uncomment):
//
// isoWeek("2012-03-05");   // expect 10
// isoWeek("2020-12-31");   // expect 53
// isoWeek("2021-01-03");   // expect 53 (Sunday still belongs to last week of 2020)
//
// loadFireData("data/fire_data.json").then(function (data) {
//   var bounds = { south: 30.0, west: 73.0, north: 32.0, east: 75.0 }; // around Lahore
//   var series = getAOISeries(data, bounds);
//   console.log("cells in AOI:", series.cellCount);
//   console.log("weeks:", series.weeks.length, "first values:", series.values.slice(0, 5));
//
//   var clim = getClimatology(series);
//   console.log("weekOfYear length:", clim.weekOfYear.length); // 53
//   console.log("mean week 44:", clim.mean[43], "std week 44:", clim.std[43]);
// }).catch(function (err) { console.error(err); });
// ---------------------------------------------------------------------------
/**
 * Return the ISO year (the year that owns the ISO week) for a date string
 * "YYYY-MM-DD". Uses the same Thursday-anchoring trick as isoWeek():
 * the ISO year of a date is the calendar year of the Thursday in its week.
 */
function isoYear(dateString) {
  var parts = dateString.split("-");
  var y = parseInt(parts[0], 10);
  var m = parseInt(parts[1], 10);
  var d = parseInt(parts[2], 10);
  var date = new Date(Date.UTC(y, m - 1, d));

  // Move to the Thursday of this ISO week (Sunday counts as day 7).
  var dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);

  return date.getUTCFullYear();
}

/**
 * Anomalies: z-score of each weekly value relative to the climatology
 * of its ISO week of year. zscore = (value - mean) / std, or 0 if std is 0.
 * Returns {weeks, values, zscores}, aligned with series.weeks.
 */
function getAnomalies(series, clim) {
  var zscores = [];

  for (var i = 0; i < series.weeks.length; i++) {
    var w = isoWeek(series.weeks[i]); // 1..53
    var mu = clim.mean[w - 1];
    var sd = clim.std[w - 1];

    if (!sd) {
      // std is 0 (or missing): no variability to compare against.
      zscores.push(0);
    } else {
      zscores.push((series.values[i] - mu) / sd);
    }
  }

  return {
    weeks: series.weeks,
    values: series.values,
    zscores: zscores
  };
}

/**
 * Critical weeks: the n weeks with the highest z-score.
 * Returns [{week, value, zscore}] sorted by zscore descending.
 */
function getCriticalWeeks(series, clim, n) {
  var anomalies = getAnomalies(series, clim);
  var items = [];

  for (var i = 0; i < anomalies.weeks.length; i++) {
    items.push({
      week: anomalies.weeks[i],
      value: anomalies.values[i],
      zscore: anomalies.zscores[i]
    });
  }

  // Sort descending by zscore.
  items.sort(function (a, b) {
    return b.zscore - a.zscore;
  });

  // Keep only the top n (guard against n larger than the list or invalid n).
  var count = Math.max(0, Math.min(n, items.length));
  return items.slice(0, count);
}

/**
 * Calendar matrix: rows = ISO years, columns = ISO weeks 1..53.
 * z[yearIndex][weekIndex] holds the weekly value for that ISO year and
 * ISO week, or null where there is no data.
 * Returns {years, weeks, z}.
 */
function getCalendarMatrix(series) {
  // Step 1: collect the distinct ISO years present in the data.
  var yearSet = {};
  for (var i = 0; i < series.weeks.length; i++) {
    yearSet[isoYear(series.weeks[i])] = true;
  }

  var years = Object.keys(yearSet).map(function (y) {
    return parseInt(y, 10);
  });
  years.sort(function (a, b) { return a - b; });

  // Map each year to its row index.
  var yearIndex = {};
  for (var yi = 0; yi < years.length; yi++) yearIndex[years[yi]] = yi;

  // Step 2: weeks axis 1..53, and a matrix filled with null.
  var weeks = [];
  for (var w = 1; w <= 53; w++) weeks.push(w);

  var z = [];
  for (var r = 0; r < years.length; r++) {
    var row = [];
    for (var c = 0; c < 53; c++) row.push(null);
    z.push(row);
  }

  // Step 3: place each weekly value at [ISO year row][ISO week - 1].
  for (var k = 0; k < series.weeks.length; k++) {
    var row_i = yearIndex[isoYear(series.weeks[k])];
    var col_i = isoWeek(series.weeks[k]) - 1;
    z[row_i][col_i] = series.values[k];
  }

  return { years: years, weeks: weeks, z: z };
}

/**
 * Peak season: the week of year with the highest mean (peakWeek), and the
 * contiguous range around it where mean >= 50% of the peak mean.
 * Does not wrap around the year boundary.
 * Returns {startWeek, endWeek, peakWeek} (week numbers 1..53).
 */
function getPeakSeason(clim) {
  // Find the index of the highest mean (first one wins on ties).
  var peakIdx = 0;
  for (var i = 1; i < clim.mean.length; i++) {
    if (clim.mean[i] > clim.mean[peakIdx]) peakIdx = i;
  }

  var threshold = 0.5 * clim.mean[peakIdx];

  // Expand left while the mean stays at or above the threshold.
  var startIdx = peakIdx;
  while (startIdx > 0 && clim.mean[startIdx - 1] >= threshold) {
    startIdx--;
  }

  // Expand right while the mean stays at or above the threshold.
  var endIdx = peakIdx;
  while (endIdx < clim.mean.length - 1 && clim.mean[endIdx + 1] >= threshold) {
    endIdx++;
  }

  return {
    startWeek: clim.weekOfYear[startIdx],
    endWeek: clim.weekOfYear[endIdx],
    peakWeek: clim.weekOfYear[peakIdx]
  };
}