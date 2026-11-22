import { Ambulance, Phone } from "lucide-react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useI18n } from "../i18n";
import { withTransition } from "../lib/motion";

/**
 * The emergency entry, everywhere: a red button in the sticky header on wide
 * screens, and a bar along the bottom of the screen on phones, where the thumb
 * already is. It opens the emergency screen as a real history entry, so Back
 * leaves it. Hidden on the emergency screen itself.
 */
export function EmergencyButton({ variant }: { variant: "header" | "bar" }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  if (location.pathname === "/" && params.get("mode") === "emergency") return null;

  function open(event: React.MouseEvent) {
    event.preventDefault();
    withTransition(() => navigate("/?mode=emergency"), "emergency");
  }

  if (variant === "header") {
    return (
      <a className="emergency-button" href="/?mode=emergency" onClick={open}>
        <Ambulance size={18} aria-hidden="true" />
        {t.emergencyShort}
      </a>
    );
  }
  return (
    <div className="emergency-bar">
      <a href="/?mode=emergency" onClick={open}>
        <Ambulance size={20} aria-hidden="true" />
        <span>{t.emergency}</span>
      </a>
      <a className="emergency-bar-call" href="tel:108" aria-label={t.emCall}>
        <Phone size={18} aria-hidden="true" />
        108
      </a>
    </div>
  );
}
