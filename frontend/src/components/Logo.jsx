/**
 * SatQuery AI brand logo.
 *
 * The supplied artwork is a full lockup (mark + wordmark + tagline), so the
 * default render is the image itself — no duplicated HTML text is drawn.
 * `withText={false}` renders the square mark only (used by the collapsed
 * sidebar, which has no room for the wordmark).
 */

const LOGO_LOCKUP = "/logo.png"; // mark + "SatQuery AI" wordmark + tagline
const LOGO_MARK = "/logo-mark.png"; // square mark (favicon / compact slots)

export default function Logo({ size = 40, withText = true, className = "" }) {
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
      style={{ height: Math.round(size * 1.5) }}
    />
  );
}