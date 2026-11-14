// docs/js/map.js
// Leaflet map with a single-rectangle AOI selector (Leaflet.draw)
// and a layer for live fire hotspots. Plain JavaScript, no modules.

// Module-level state shared by the global functions below
var map = null;            // the Leaflet map instance
var drawnItems = null;     // feature group holding the single AOI rectangle
var livePointsLayer = null; // layer group holding live hotspot markers

/**
 * Convert a Leaflet LatLngBounds into the plain bounds object
 * used by the rest of the app: {south, west, north, east}.
 */
function boundsToObject(latLngBounds) {
  return {
    south: latLngBounds.getSouth(),
    west: latLngBounds.getWest(),
    north: latLngBounds.getNorth(),
    east: latLngBounds.getEast()
  };
}

/**
 * Initialise the map inside the div with id mapDivId.
 * onAOIChange(bounds) is called when the user draws or edits a rectangle,
 * and onAOIChange(null) is called when the rectangle is deleted.
 */
function initMap(mapDivId, onAOIChange) {
  // Create the map with the canvas renderer so thousands of circle
  // markers stay fast
  map = L.map(mapDivId, {
    center: [31, 74],
    zoom: 6,
    renderer: L.canvas()
  });

  // OpenStreetMap base tiles with attribution
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  // Feature group that holds the (single) AOI rectangle
  drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  // Draw toolbar: rectangle only; edit and delete tools enabled
  var drawControl = new L.Control.Draw({
    draw: {
      polyline: false,
      polygon: false,
      circle: false,
      marker: false,
      circlemarker: false,
      rectangle: {
        shapeOptions: { color: '#1565c0', weight: 2 }
      }
    },
    edit: {
      featureGroup: drawnItems,
      edit: true,
      remove: true
    }
  });
  map.addControl(drawControl);

  // Layer group for live hotspot markers
  livePointsLayer = L.layerGroup().addTo(map);

  // A new rectangle was drawn: keep only this one
  map.on(L.Draw.Event.CREATED, function (e) {
    // Remove the previous rectangle, if any
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    if (typeof onAOIChange === 'function') {
      onAOIChange(boundsToObject(e.layer.getBounds()));
    }
  });

  // The rectangle was edited: report its new bounds
  map.on(L.Draw.Event.EDITED, function () {
    var bounds = null;
    drawnItems.eachLayer(function (layer) {
      bounds = layer.getBounds();
    });
    if (bounds && typeof onAOIChange === 'function') {
      onAOIChange(boundsToObject(bounds));
    }
  });

  // The rectangle was deleted: report null
  map.on(L.Draw.Event.DELETED, function () {
    if (typeof onAOIChange === 'function') {
      onAOIChange(null);
    }
  });
}

/**
 * Draw live hotspots as small circle markers, replacing any old ones.
 * points: array of [lat, lon, acq_date, acq_time, frp]
 */
function showLivePoints(points) {
  if (!livePointsLayer) return;

  // Remove the previous markers
  livePointsLayer.clearLayers();

  (points || []).forEach(function (p) {
    var lat = p[0];
    var lon = p[1];
    var date = p[2];
    var time = String(p[3] == null ? '' : p[3]);
    var frp = p[4];

    // Pad acquisition time to 4 digits (e.g. 530 -> "0530")
    while (time.length < 4) time = '0' + time;

    var marker = L.circleMarker([lat, lon], {
      radius: 3,
      color: '#7f1d00',      // thin dark stroke
      weight: 1,
      fillColor: '#ff4500',  // orange-red fill
      fillOpacity: 0.7
    });

    marker.bindPopup('Date: ' + date + ' ' + time + ' UTC, FRP: ' + frp + ' MW');
    livePointsLayer.addLayer(marker);
  });
}

/**
 * Remove all live hotspot markers from the map.
 */
function clearLivePoints() {
  if (livePointsLayer) {
    livePointsLayer.clearLayers();
  }
}