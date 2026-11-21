export function MapLegend() {
  return (
    <div className="map-legend" aria-label="Map score legend">
      <span>
        <i className="legend-marker legend-marker-strong" /> 85+
      </span>
      <span>
        <i className="legend-marker legend-marker-mid" /> 70–84
      </span>
      <span>
        <i className="legend-marker legend-marker-low" /> &lt;70
      </span>
    </div>
  );
}
