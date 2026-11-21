import { Activity } from "lucide-react";

export function Brand() {
  return (
    <a className="brand" href="/" aria-label="CarePath home">
      <span className="brand-mark" aria-hidden="true">
        <Activity size={21} strokeWidth={2.5} />
      </span>
      <span className="brand-copy">
        <strong>CarePath</strong>
        <span>Evidence-led care search</span>
      </span>
    </a>
  );
}
