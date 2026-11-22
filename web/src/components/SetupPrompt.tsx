import { ArrowRight, X } from "lucide-react";
import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { saveProfile, useProfile } from "../lib/profile";

/**
 * The only invitation to set up: one line under the search, shown until the
 * person finishes setup or says "Not now". It never opens on its own.
 */
export function SetupPrompt() {
  const { t } = useI18n();
  const profile = useProfile();
  if (profile.onboardingDone || profile.promptDismissed) return null;
  return (
    <p className="setup-prompt">
      <span>{t.setupPrompt}</span>
      <Link to="/welcome">
        {t.setupStart}
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
      <button
        type="button"
        className="icon-button setup-dismiss"
        aria-label={t.setupDismiss}
        title={t.setupDismiss}
        onClick={() => saveProfile({ promptDismissed: true })}
      >
        <X size={16} />
      </button>
    </p>
  );
}
