/**
 * Raahi (राही, "traveller on the path") — CarePath's mascot.
 *
 * A map pin with a face and a single leaf: the pin says "care near you", the
 * leaf ties it to Sprout. The name reads the same in Hindi and English. Like Sprout's mascot, Raahi is where the product signs
 * its name (header, footer, favicon) and the voice that speaks at the moments
 * a person might be unsure: the first screen, while results load, when nothing
 * matches, and beside what we could not confirm.
 *
 * Colours come from the --raahi-* tokens so Raahi follows light and dark themes.
 */

export type RaahiMood = "happy" | "thinking" | "concerned";

const PIN_PATH =
  "M80 172C66 148 24 120 24 76a56 56 0 1 1 112 0c0 44-42 72-56 96z";

function Face({ mood }: { mood: RaahiMood }) {
  if (mood === "thinking") {
    return (
      <g className="raahi-face">
        <circle cx="63" cy="70" r="7" />
        <circle cx="103" cy="70" r="7" />
        <path d="M70 98h22" fill="none" strokeWidth="6" strokeLinecap="round" />
      </g>
    );
  }
  if (mood === "concerned") {
    return (
      <g className="raahi-face">
        <path d="M50 62l15-7M110 62l-15-7" fill="none" strokeWidth="5" strokeLinecap="round" />
        <circle cx="60" cy="74" r="7" />
        <circle cx="100" cy="74" r="7" />
        <path d="M68 100q12-6 24 0" fill="none" strokeWidth="6" strokeLinecap="round" />
      </g>
    );
  }
  return (
    <g className="raahi-face">
      <circle cx="60" cy="72" r="7" />
      <circle cx="100" cy="72" r="7" />
      <path d="M64 92q16 13 32 0" fill="none" strokeWidth="6" strokeLinecap="round" />
    </g>
  );
}

export function Raahi({
  size = 120,
  mood = "happy",
  className = "",
}: {
  size?: number;
  mood?: RaahiMood;
  className?: string;
}) {
  return (
    <svg
      className={`raahi raahi--${mood} ${className}`}
      viewBox="0 0 160 180"
      width={size}
      height={(size * 180) / 160}
      aria-hidden="true"
      focusable="false"
    >
      <g className="raahi-leaf">
        <path d="M80 26V10" fill="none" strokeWidth="6" strokeLinecap="round" />
        <path d="M80 14c4-12 18-17 30-13-2 13-15 19-28 17z" />
      </g>
      <path className="raahi-body" d={PIN_PATH} />
      <path className="raahi-rim" d={PIN_PATH} fill="none" strokeWidth="7" />
      <g className="raahi-cheeks">
        <ellipse cx="46" cy="90" rx="10" ry="6" />
        <ellipse cx="114" cy="90" rx="10" ry="6" />
      </g>
      <Face mood={mood} />
    </svg>
  );
}

/** Raahi at icon size: same pin, leaf and face, simplified to read at 20px. */
export function RaahiMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      className="raahi raahi-mark"
      viewBox="0 0 32 36"
      width={size}
      height={(size * 36) / 32}
      aria-hidden="true"
      focusable="false"
    >
      <g className="raahi-leaf">
        <path d="M16 6.4V2.6" fill="none" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M16 3.4c.9-2.6 3.9-3.6 6.5-2.8-.4 2.8-3.2 4.1-6 3.6z" />
      </g>
      <path
        className="raahi-body"
        d="M16 34.5c-3-5-11.5-10.6-11.5-19.3a11.5 11.5 0 1 1 23 0c0 8.7-8.5 14.3-11.5 19.3z"
      />
      <path
        className="raahi-rim"
        d="M16 34.5c-3-5-11.5-10.6-11.5-19.3a11.5 11.5 0 1 1 23 0c0 8.7-8.5 14.3-11.5 19.3z"
        fill="none"
        strokeWidth="1.6"
      />
      <g className="raahi-face">
        <circle cx="12.4" cy="14.6" r="1.5" />
        <circle cx="19.6" cy="14.6" r="1.5" />
        <path d="M13 18.6q3 2.4 6 0" fill="none" strokeWidth="1.6" strokeLinecap="round" />
      </g>
    </svg>
  );
}

/** Raahi with a speech bubble: the mascot used as a label for a short message. */
export function RaahiSays({
  children,
  mood = "happy",
  size = 72,
  className = "",
}: {
  children: React.ReactNode;
  mood?: RaahiMood;
  size?: number;
  className?: string;
}) {
  return (
    <div className={`raahi-says ${className}`}>
      <Raahi size={size} mood={mood} />
      <div className="raahi-bubble">{children}</div>
    </div>
  );
}

/** RaahiMark as markup, for Leaflet icons that take an HTML string. */
export const RAAHI_MARK_HTML = `<svg class="raahi raahi-mark" viewBox="0 0 32 36" width="30" height="34" aria-hidden="true"><g class="raahi-leaf"><path d="M16 6.4V2.6" fill="none" stroke-width="1.6" stroke-linecap="round"/><path d="M16 3.4c.9-2.6 3.9-3.6 6.5-2.8-.4 2.8-3.2 4.1-6 3.6z"/></g><path class="raahi-body" d="M16 34.5c-3-5-11.5-10.6-11.5-19.3a11.5 11.5 0 1 1 23 0c0 8.7-8.5 14.3-11.5 19.3z"/><path class="raahi-rim" d="M16 34.5c-3-5-11.5-10.6-11.5-19.3a11.5 11.5 0 1 1 23 0c0 8.7-8.5 14.3-11.5 19.3z" fill="none" stroke-width="1.6"/><g class="raahi-face"><circle cx="12.4" cy="14.6" r="1.5"/><circle cx="19.6" cy="14.6" r="1.5"/><path d="M13 18.6q3 2.4 6 0" fill="none" stroke-width="1.6" stroke-linecap="round"/></g></svg>`;
