/**
 * Design tokens for the submission film.
 *
 * The brief, pinned by me: an **inspection record** for a machine that rewrites itself.
 * Audience: engineers and judges who do not trust a system's own report of success. The
 * film's single job: make one refusal legible, with its arithmetic, in sixty seconds.
 *
 * The subject's own world is paperwork — the lab record, the certificate of analysis, the
 * form that gets stamped. So this is paper, not a console. Deliberately not the three
 * looks that AI work currently clusters around: not warm cream with a serif and a
 * terracotta accent, not a near-black screen with one acid accent (which is what the
 * previous cut was), not a newspaper broadsheet.
 *
 * Colour, five values and a rule:
 *   paper   #f3f3ef  a cool grey-white, not the warm cream default
 *   ink     #17191c  all text
 *   rule    #d8d8d1  hairlines only
 *   stamp   #b8361a  refusals, and nothing else, ever
 *   pass    #2c6046  the one accepted thing, and nothing else
 *
 * Type, two faces with clearly separated jobs:
 *   Archivo 700     statements; tight tracking, no softening
 *   Courier Prime   every measurement, every ledger line: a typewriter face, because
 *                   this is a record rather than a user interface
 *
 * Signature element: the **stamp**. The gate's word stamp-framed in vermilion and set
 * slightly off-square, landing at the moment of refusal. One memorable thing; everything
 * around it stays quiet.
 */

export const COLORS = {
  paper: "#f3f3ef",
  paperDeep: "#e9e9e3",
  ink: "#17191c",
  rule: "#d8d8d1",
  ruleBright: "#b9bab1",
  stamp: "#b8361a",
  pass: "#2c6046",
  measure: "#6f736a",
};

export const FONTS = {
  display: '"Archivo", "Helvetica Neue", Arial, sans-serif',
  record: '"Courier Prime", "Courier New", monospace',
};

export const KICKER: React.CSSProperties = {
  fontFamily: FONTS.record,
  fontSize: 19,
  fontWeight: 700,
  letterSpacing: "0.22em",
  textTransform: "uppercase",
  color: COLORS.measure,
};

export const STATEMENT: React.CSSProperties = {
  fontFamily: FONTS.display,
  fontWeight: 700,
  fontSize: 52,
  lineHeight: 1.1,
  letterSpacing: "-0.025em",
  color: COLORS.ink,
};

export const MEASURE: React.CSSProperties = {
  fontFamily: FONTS.record,
  fontSize: 22,
  lineHeight: 1.62,
  fontVariantNumeric: "tabular-nums",
  color: COLORS.ink,
};

export const MEASURE_DIM: React.CSSProperties = { ...MEASURE, color: COLORS.measure };
