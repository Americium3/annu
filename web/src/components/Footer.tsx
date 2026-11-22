import { useI18n } from "../i18n";
import { USE_DEMO } from "../lib/api";
import { AnnuMark } from "./AnnuMark";

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <AnnuMark size={24} />
          <strong>Annu</strong>
        </div>
        <p>
          {USE_DEMO ? t.prototypeNote : t.liveNote} {t.footerNote}
        </p>
        <nav className="footer-links" aria-label={t.footerNav}>
          <a href="#how-it-works">{t.footerMethod}</a>
          <span>© 2026 Annu</span>
        </nav>
      </div>
    </footer>
  );
}
