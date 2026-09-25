/**
 * SatQuery AI brand logo.
 *
 * The supplied artwork is a full lockup (mark + wordmark + tagline), so the
 * default render is the image itself — no duplicated HTML text is drawn.
 * `withText={false}` renders the square mark only (used by the collapsed
 * sidebar, which has no room for the wordmark).
 *
 * Sizing note: in the artwork the wordmark is only ~35% of the image height and
 * the tagline ~7%, so the lockup needs real height before its text resolves.
 * 60px is the floor at which the wordmark stays crisp (enforced below); the
 * tagline needs ~66px. Do not shrink a lockup back to an unreadable size.
 */

const LOGO_LOCKUP = "/logo.png"; // mark + "SatQuery AI" wordmark + tagline
const LOGO_MARK = "/logo-mark.png"; // square mark (favicon / compact slots)

/** Height floor: below this the lockup's wordmark stops being readable. */
const LOCKUP_MIN_HEIGHT = 60;
/** `size` is the mark's box; the ~3:1 lockup has to be noticeably taller. */
const LOCKUP_SCALE = 1.5;

export default function Logo({ size = 44, withText = true, className = "" }) {
  if (!withText) {
    return (
      <img
        src={LOGO_MARK}
        alt="SatQuery AI"
        draggable="false"
        className={`brand-logo-mark shrink-0 select-none ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <img
      src={LOGO_LOCKUP}
      alt="SatQuery AI — from satellites to solutions"
      draggable="false"
      className={`brand-logo shrink-0 select-none ${className}`}
      style={{ height: Math.max(Math.round(size * LOCKUP_SCALE), LOCKUP_MIN_HEIGHT) }}
    />
  );
}