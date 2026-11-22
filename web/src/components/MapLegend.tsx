import { useI18n } from "../i18n";

export function MapLegend() {
  const { t } = useI18n();
  return (
    <dl className="map-legend" aria-label={t.mapLegend}>
      <div>
        <dt className="legend-pin legend-pin-strong" />
        <dd>{t.legendStrong} · 85+</dd>
      </div>
      <div>
        <dt className="legend-pin legend-pin-mid" />
        <dd>{t.legendMid} · 70–84</dd>
      </div>
      <div>
        <dt className="legend-pin legend-pin-low" />
        <dd>{t.legendLow} · &lt;70</dd>
      </div>
    </dl>
  );
}
