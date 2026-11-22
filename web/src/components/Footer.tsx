import { useI18n } from "../i18n";
import { RaahiMark } from "./Raahi";

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <RaahiMark size={24} />
          <strong>CarePath</strong>
        </div>
        <p>{t.footerNote}</p>
        <nav className="footer-links" aria-label="Footer">
          <a href="#how-it-works">{t.footerMethod}</a>
          <span>© 2026 CarePath</span>
        </nav>
      </div>
    </footer>
  );
}
