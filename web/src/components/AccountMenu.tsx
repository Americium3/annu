import { CircleUserRound, LogOut, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../i18n";
import { formatPhone, signOut, useSession } from "../lib/auth";

/** "Sign in" for guests; for a signed-in person, a small menu (as in Sprout's header). */
export function AccountMenu() {
  const { t } = useI18n();
  const session = useSession();
  const location = useLocation();
  const menuRef = useRef<HTMLDetailsElement>(null);
  const here = `${location.pathname}${location.search}`;

  // Close the menu when clicking elsewhere or pressing Escape.
  useEffect(() => {
    function close(event: Event) {
      const menu = menuRef.current;
      if (!menu?.open) return;
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !menu.contains(event.target as Node)) {
        menu.open = false;
      }
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, []);

  if (!session) {
    if (location.pathname === "/sign-in") return null;
    return (
      <Link className="header-link" to={`/sign-in?return_to=${encodeURIComponent(here)}`}>
        {t.signIn}
      </Link>
    );
  }

  return (
    <details className="account-menu" ref={menuRef}>
      <summary className="icon-button" aria-label={t.account} title={t.account}>
        <CircleUserRound size={20} />
      </summary>
      <div className="account-card">
        <p>
          <small>{t.signedInAs}</small>
          <strong>{formatPhone(session.phone, true)}</strong>
        </p>
        <Link to="/welcome?again=1" onClick={() => menuRef.current?.removeAttribute("open")}>
          <SlidersHorizontal size={16} aria-hidden="true" />
          {t.editPreferences}
        </Link>
        <button
          type="button"
          onClick={() => {
            signOut();
            menuRef.current?.removeAttribute("open");
          }}
        >
          <LogOut size={16} aria-hidden="true" />
          {t.signOut}
        </button>
      </div>
    </details>
  );
}
