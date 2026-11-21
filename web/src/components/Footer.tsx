import { Activity, ShieldCheck } from "lucide-react";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <span className="footer-mark">
            <Activity size={18} />
          </span>
          <div>
            <strong>CarePath</strong>
            <span>Evidence-led care search</span>
          </div>
        </div>
        <p>
          <ShieldCheck size={15} />
          Prototype with illustrative facilities and sources. Not medical advice.
        </p>
        <div className="footer-links">
          <a href="#how-it-works">Methodology</a>
          <a href="#evidence">Evidence policy</a>
          <span>© 2026 CarePath</span>
        </div>
      </div>
    </footer>
  );
}
