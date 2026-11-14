/**
 * charts.js
 * Global chart-drawing functions for the Burning Activity Calendar.
 * Requires Plotly.js (2.x) to be loaded globally before this script.
 */

/**
 * Draws the calendar heatmap (years x ISO weeks).
 *
 * @param {string} divId   id of the target <div> element
 * @param {{years: Array<number|string>, weeks: number[], z: Array<Array<number|null>>}} matrix
 *        z[i][j] is the value for years[i], weeks[j]; null where no data.
 */
function drawCalendarHeatmap(divId, matrix) {
  // Years are treated as categories, so convert them to strings
  var years = matrix.years.map(function (y) { return String(y); });

  // Build hover text matrix: "Year, Week, Value" with value rounded to 1 decimal
  var hoverText = matrix.z.map(function (row, i) {
    return row.map(function (v, j) {
      if (v === null || v === undefined) return "";
      return "Year: " + years[i] +
             "<br>Week: " + matrix.weeks[j] +
             "<br>Value: " + Number(v).toFixed(1);
    });
  });

  // Heatmap trace
  var trace = {
    type: "heatmap",
    x: matrix.weeks,
    y: years,
    z: matrix.z,
    text: hoverText,
    hoverinfo: "text",       // show only our custom text
    hoverongaps: false,      // no hover on cells without data
    xgap: 1,                 // 1px gap between cells
    ygap: 1,
    colorscale: "YlOrRd",
    colorbar: {
      title: { text: "Fires (harmonized)", side: "right" }
    }
  };

  // Layout: tight margins, reversed y axis (oldest year on top)
  var layout = {
    title: { text: "Burning Activity Calendar" },
    height: 360,
    margin: { l: 60, r: 20, t: 50, b: 50 },
    xaxis: {
      title: { text: "ISO week of year" }
    },
    yaxis: {
      title: { text: "Year" },
      type: "category",      // treat years as discrete labels
      autorange: "reversed"  // oldest year at the top
    }
  };

  // responsive: true makes the chart resize with its container
  var config = { responsive: true };

  // Plotly.react replaces any existing chart in the div on repeat calls
  Plotly.react(divId, [trace], layout, config);
}
/**
 * Draws the climatology chart: mean fire activity per ISO week of year,
 * with a +/- 1 std band and a shaded peak-season rectangle.
 *
 * @param {string} divId  id of the target <div> element
 * @param {{weekOfYear: number[], mean: number[], std: number[]}} clim
 * @param {{startWeek: number, endWeek: number, peakWeek: number}} peak
 */
function drawClimatology(divId, clim, peak) {
  // Band bounds: lower never goes below 0, upper is mean + std
  var lower = clim.mean.map(function (m, i) {
    return Math.max(0, m - clim.std[i]);
  });
  var upper = clim.mean.map(function (m, i) {
    return m + clim.std[i];
  });

  // Trace 1: lower bound (invisible line, acts as the base of the band)
  var lowerTrace = {
    type: "scatter",
    mode: "lines",
    x: clim.weekOfYear,
    y: lower,
    line: { width: 0 },
    hoverinfo: "skip",
    showlegend: false
  };

  // Trace 2: upper bound, filled down to the lower trace ("tonexty")
  var upperTrace = {
    type: "scatter",
    mode: "lines",
    x: clim.weekOfYear,
    y: upper,
    line: { width: 0 },
    fill: "tonexty",
    fillcolor: "rgba(253, 174, 97, 0.3)",  // light orange band
    hoverinfo: "skip",
    showlegend: false
  };

  // Trace 3: the mean line, drawn on top of the band
  var meanTrace = {
    type: "scatter",
    mode: "lines",
    x: clim.weekOfYear,
    y: clim.mean,
    line: { color: "#d94801", width: 2 },
    name: "Mean",
    hovertemplate: "Week %{x}<br>Mean: %{y:.1f}<extra></extra>",
    showlegend: false
  };

  // Peak season shading and label (only if peak info is available)
  var shapes = [];
  var annotations = [];
  if (peak && peak.startWeek != null && peak.endWeek != null) {
    shapes.push({
      type: "rect",
      xref: "x",
      yref: "paper",     // y spans the full plot height (0 to 1)
      x0: peak.startWeek,
      x1: peak.endWeek,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(215, 48, 39, 0.12)",
      line: { width: 0 },
      layer: "below"     // keep the shading behind the data
    });
    annotations.push({
      x: (peak.startWeek + peak.endWeek) / 2,  // centre of the peak window
      xref: "x",
      y: 1,
      yref: "paper",
      text: "Peak season",
      showarrow: false,
      yanchor: "bottom",
      font: { size: 11, color: "#b30000" }
    });
  }

  // Layout: height 300px, tight margins
  var layout = {
    title: { text: "Typical fire activity by week of year" },
    height: 300,
    margin: { l: 55, r: 20, t: 55, b: 45 },
    xaxis: { title: { text: "ISO week of year" } },
    yaxis: { title: { text: "Harmonized fire count" }, rangemode: "tozero" },
    shapes: shapes,
    annotations: annotations
  };

  // Plotly.react replaces any existing chart in the div on repeat calls
  Plotly.react(divId, [lowerTrace, upperTrace, meanTrace], layout, { responsive: true });
}

/**
 * Draws the anomaly chart: z-score per week as bars,
 * red when z > 2 (notable), gray otherwise.
 *
 * @param {string} divId  id of the target <div> element
 * @param {{weeks: string[], values: number[], zscores: number[]}} anomalies
 *        weeks are "YYYY-MM-DD" date strings
 */
function drawAnomalies(divId, anomalies) {
  // Color each bar individually: red above the threshold, gray otherwise
  var threshold = 2;
  var colors = anomalies.zscores.map(function (z) {
    return z > threshold ? "#d73027" : "#9e9e9e";
  });

  // Bar trace; custom data lets the hover show the raw value too
  var trace = {
    type: "bar",
    x: anomalies.weeks,
    y: anomalies.zscores,
    marker: { color: colors },
    customdata: anomalies.values,
    hovertemplate: "Week of %{x}<br>z-score: %{y:.2f}<br>Value: %{customdata:.1f}<extra></extra>",
    showlegend: false
  };

  // Horizontal dashed line at z = 2 spanning the full plot width
  var shapes = [{
    type: "line",
    xref: "paper",   // x spans the full plot width (0 to 1)
    yref: "y",       // y is in data units
    x0: 0,
    x1: 1,
    y0: threshold,
    y1: threshold,
    line: { color: "#d73027", width: 1.5, dash: "dash" }
  }];

  // Layout: height 300px, tight margins
  var layout = {
    title: { text: "Unusual periods (z-score, 2 = notable)" },
    height: 300,
    margin: { l: 55, r: 20, t: 55, b: 45 },
    xaxis: { type: "date" },
    yaxis: { title: { text: "z-score" }, zeroline: true },
    shapes: shapes
  };

  // Plotly.react replaces any existing chart in the div on repeat calls
  Plotly.react(divId, [trace], layout, { responsive: true });
}