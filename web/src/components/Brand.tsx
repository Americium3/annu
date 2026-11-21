import { useI18n } from "../i18n";
import { RaahiMark } from "./Raahi";

export function Brand() {
  const { t } = useI18n();
  return (
    <a className="brand" href="/" aria-label={t.homeLabel}>
      <RaahiMark size={26} />
      <span className="brand-name">CarePath</span>
    </a>
  );
}
