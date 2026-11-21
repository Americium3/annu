import {
  BadgeCheck,
  CircleAlert,
  FileSearch,
  GitCompareArrows,
  MapPin,
  SlidersHorizontal,
} from "lucide-react";

const steps = [
  {
    icon: FileSearch,
    number: "01",
    title: "Search by real need",
    copy: "Describe the service in everyday language, from dialysis to emergency C-section.",
  },
  {
    icon: MapPin,
    number: "02",
    title: "Resolve the location",
    copy: "See exactly which city, district or PIN the comparison is using before results appear.",
  },
  {
    icon: GitCompareArrows,
    number: "03",
    title: "Compare the evidence",
    copy: "Review quotes, source types and score contributions. Strong claims need clear support.",
  },
];

export function TrustSection() {
  return (
    <>
      <section className="trust-section" id="how-it-works">
        <div className="trust-intro">
          <span className="section-eyebrow">Designed for a difficult decision</span>
          <h2>
            A recommendation is only useful
            <br />
            when you can see <em>why.</em>
          </h2>
          <p>
            CarePath separates popularity from evidence. Each candidate is built from source
            fields, exact quotes and transparent uncertainty.
          </p>
        </div>
        <div className="principles">
          <div className="principle">
            <span className="principle-icon">
              <BadgeCheck size={20} />
            </span>
            <div>
              <strong>No fake certainty</strong>
              <p>Claims stay labeled as claims unless corroborated.</p>
            </div>
          </div>
          <div className="principle">
            <span className="principle-icon">
              <CircleAlert size={20} />
            </span>
            <div>
              <strong>Uncertainty stays visible</strong>
              <p>Conflicts, stale sources and missing data are surfaced.</p>
            </div>
          </div>
          <div className="principle">
            <span className="principle-icon">
              <SlidersHorizontal size={20} />
            </span>
            <div>
              <strong>Built to evolve</strong>
              <p>The UI contract supports future ML ranking without a rewrite.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="steps-section">
        <div className="steps-heading">
          <span className="section-eyebrow">How it works</span>
          <h2>From need to next step</h2>
        </div>
        <div className="steps-grid">
          {steps.map(({ icon: Icon, number, title, copy }) => (
            <article className="step-card" key={number}>
              <div className="step-top">
                <span className="step-icon">
                  <Icon size={21} />
                </span>
                <span className="step-number">{number}</span>
              </div>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
