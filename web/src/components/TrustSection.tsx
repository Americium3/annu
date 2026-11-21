import { useI18n } from "../i18n";
import { RaahiSays } from "./Raahi";

/** How ranking works: one short explanation and a plain numbered list. */
export function TrustSection() {
  const { t } = useI18n();
  const steps = [
    [t.how1Title, t.how1Body],
    [t.how2Title, t.how2Body],
    [t.how3Title, t.how3Body],
    [t.how4Title, t.how4Body],
  ];

  return (
    <section className="how-section" id="how-it-works" aria-labelledby="how-title">
      <div className="how-inner">
        <div className="how-intro">
          <h2 id="how-title">{t.howTitle}</h2>
          <p>{t.howLede}</p>
          <RaahiSays className="how-raahi" size={60}>
            {t.howRaahi}
          </RaahiSays>
        </div>
        <ol className="how-list">
          {steps.map(([title, body]) => (
            <li key={title}>
              <h3>{title}</h3>
              <p>{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
