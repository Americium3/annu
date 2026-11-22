import { Moon, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";
import { useI18n, type Lang } from "../i18n";
import { USE_DEMO } from "../lib/api";
import { AccountMenu } from "./AccountMenu";
import { EmergencyButton } from "./EmergencyButton";
import { withTransition } from "../lib/motion";
import { Brand } from "./Brand";

const languages: Array<{ value: Lang; label: string }> = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिंदी" },
];

export function Header() {
  const { theme, toggle } = useTheme();
  const { t, lang, setLang } = useI18n();
  const themeLabel = theme === "dark" ? t.themeToLight : t.themeToDark;

  return (
    <>
      <a className="skip-link" href="#search">
        {t.skipToSearch}
      </a>
      <div className="top-strip">
        <div className="top-strip-inner">
          <p className="top-strip-note">{USE_DEMO ? t.prototypeNote : t.liveNote}</p>
        </div>
      </div>
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <div className="header-actions">
            <EmergencyButton variant="header" />
            <AccountMenu />
            <div className="lang-switch" role="group" aria-label={t.language}>
              {languages.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  lang={option.value}
                  aria-pressed={lang === option.value}
                  onClick={() => withTransition(() => setLang(option.value), "fade")}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label={themeLabel}
              title={themeLabel}
              onClick={(event) => {
                // The new theme spreads out from the button that was pressed.
                const root = document.documentElement;
                root.style.setProperty("--reveal-x", `${event.clientX}px`);
                root.style.setProperty("--reveal-y", `${event.clientY}px`);
                withTransition(toggle, "theme");
              }}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>
      </header>
      <EmergencyButton variant="bar" />
    </>
  );
}
