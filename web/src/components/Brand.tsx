import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { RaahiMark } from "./Raahi";

export function Brand() {
  const { t } = useI18n();
  return (
    <Link className="brand" to="/" aria-label={t.homeLabel}>
      <RaahiMark size={26} />
      <span className="brand-name">CarePath</span>
    </Link>
  );
}
