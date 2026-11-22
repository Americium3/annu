import { Moon, Phone, Sun } from "lucide-react";
import { useTheme } from "../hooks/useTheme";
import { useI18n, type Lang } from "../i18n";
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
      {/* Always visible: the one thing this site must never get in the way of. */}
      <div className="top-strip">
        <div className="top-strip-inner">
          <p className="top-strip-note">{t.prototypeNote}</p>
          <a className="top-strip-emergency" href="tel:108">
            <Phone size={14} aria-hidden="true" />
            <span>{t.emergency}</span> <strong>{t.emergencyCall}</strong>
          </a>
        </div>
      </div>
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <div className="header-actions">
            <div className="lang-switch" role="group" aria-label={t.language}>
              {languages.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  lang={option.value}
                  aria-pressed={lang === option.value}
                  onClick={() => setLang(option.value)}
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
              onClick={toggle}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>
      </header>
    </>
  );
}
