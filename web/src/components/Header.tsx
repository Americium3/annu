import { CircleHelp, Database, Menu, Moon, Sun, X } from "lucide-react";
import { useState } from "react";
import { useTheme } from "../hooks/useTheme";
import { Brand } from "./Brand";

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggle } = useTheme();
  const nextLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <header className="site-header">
      <div className="header-inner">
        <Brand />
        <nav className={`primary-nav ${menuOpen ? "is-open" : ""}`} aria-label="Primary">
          <a className="nav-link is-active" href="#search">
            Find care
          </a>
          <a className="nav-link" href="#how-it-works">
            How it works
          </a>
          <a className="nav-link" href="#evidence">
            Our evidence
          </a>
        </nav>
        <div className="header-actions">
          <span className="demo-pill">
            <Database size={13} aria-hidden="true" />
            Demo data
          </span>
          <button
            className="icon-button theme-button"
            type="button"
            aria-label={nextLabel}
            title={nextLabel}
            onClick={toggle}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <a
            className="icon-button help-button"
            href="#how-it-works"
            aria-label="Help and information"
          >
            <CircleHelp size={19} />
          </a>
          <button
            className="icon-button menu-button"
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>
      </div>
    </header>
  );
}
