import { Link } from "react-router-dom";
import { useI18n } from "../i18n";
import { AnnuMark } from "./AnnuMark";

export function Brand() {
  const { t } = useI18n();
  return (
    <Link className="brand" to="/" aria-label={t.homeLabel}>
      <AnnuMark size={26} />
      <span className="brand-name">Annu</span>
    </Link>
  );
}
