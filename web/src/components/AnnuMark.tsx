/**
 * Annu's logo: the Devanagari letter अ ("a", the first letter of अन्नू) held
 * in the centre of a soft green medical cross. The cross says "healthcare" at a
 * glance, in the green people in India know from clinics and chemists; the
 * letter is set small enough to leave the cross room to read as a cross.
 *
 * The letter is an outline of Noto Sans Devanagari ExtraBold plus a full
 * headline (shirorekha), so the mark looks the same before web fonts load and
 * in the favicon (public/favicon.svg holds the same drawing with light-theme
 * colours). Colours come from the --mark-* tokens.
 */

/** Rounded plus: arms 14 wide, outer corners r3.5, inner corners r2. */
const CROSS =
  "M9 3.5A3.5 3.5 0 0 1 12.5 0H19.5A3.5 3.5 0 0 1 23 3.5V7A2 2 0 0 0 25 9H28.5A3.5 3.5 0 0 1 32 12.5V19.5A3.5 3.5 0 0 1 28.5 23H25A2 2 0 0 0 23 25V28.5A3.5 3.5 0 0 1 19.5 32H12.5A3.5 3.5 0 0 1 9 28.5V25A2 2 0 0 0 7 23H3.5A3.5 3.5 0 0 1 0 19.5V12.5A3.5 3.5 0 0 1 3.5 9H7A2 2 0 0 0 9 7Z";

const LETTER_A =
  "M20.97 14.12V21.3H18.7V17.8Q18.65 17.81 18.59 17.81Q18.17 17.9 17.74 17.9Q17.48 17.9 17.22 17.87Q17.23 17.98 17.23 18.11Q17.23 19.31 16.48 19.98Q15.72 20.65 14.36 20.65Q13.37 20.65 12.58 20.27Q11.78 19.89 11.09 18.98Q10.4 18.07 9.75 16.48L11.47 15.62Q12.13 17.28 12.73 18.05Q13.33 18.82 14.08 18.82Q14.57 18.82 14.84 18.58Q15.11 18.34 15.11 17.88Q15.11 17.45 14.81 17.06Q14.77 17.02 14.72 16.96Q14.1 17.12 13.33 17.16L13.05 15.55Q13.76 15.48 14.15 15.35Q14.54 15.23 14.69 15.06Q14.84 14.88 14.84 14.64Q14.84 14.31 14.62 14.16Q14.39 14 14 14Q13.6 14 13.17 14.12Q12.75 14.24 12.32 14.47L11.73 12.81Q12.29 12.52 12.94 12.35Q13.59 12.19 14.32 12.19Q15.27 12.19 15.87 12.49Q16.47 12.79 16.74 13.31Q17.02 13.83 17.02 14.51Q17.02 15.5 16.32 16.15Q16.43 16.17 16.51 16.17Q16.84 16.21 17.26 16.21Q17.81 16.21 18.31 16.1Q18.52 16.07 18.7 15.99V14.12H17.84V12.33H22.25V14.12Z";

export function AnnuMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      className="annu-mark"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <path className="annu-mark-cross" d={CROSS} />
      <g className="annu-mark-letter">
        <path d={LETTER_A} />
        <rect x="9.25" y="10.7" width="13.5" height="1.69" rx="0.84" />
      </g>
    </svg>
  );
}
