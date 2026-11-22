import { useI18n } from "../i18n";

/** How ranking works, folded away: there for anyone who asks, never in the way. */
export function TrustSection() {
  const { t } = useI18n();
  const steps = [
    [t.how1Title, t.how1Body],
    [t.how2Title, t.how2Body],
    [t.how3Title, t.how3Body],
    [t.how4Title, t.how4Body],
  ];

  return (
    <section className="how-section" id="how-it-works" aria-label={t.howToggle}>
      <details className="how-inner">
        <summary>{t.howToggle}</summary>
        <div className="how-body">
          <p>{t.howLede}</p>
          <ol className="how-list">
            {steps.map(([title, body]) => (
              <li key={title}>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </details>
    </section>
  );
}
