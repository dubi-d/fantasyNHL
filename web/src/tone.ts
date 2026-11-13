// The terminal's gradient: neutral grey at 0, green toward +1, red toward -1.
const NEUTRAL = [60, 60, 60];
const GOOD = [0, 135, 0];
const BAD = [175, 0, 0];

/** Background color of a diverging tone in [-1, 1]. */
export function toneColor(tone: number): string {
  const end = tone >= 0 ? GOOD : BAD;
  const weight = Math.min(Math.abs(tone), 1);
  const channels = NEUTRAL.map((from, i) =>
    Math.round(from + weight * (end[i] - from)),
  );
  return `rgb(${channels.join(",")})`;
}

/** CSS classes of space-separated tone tags ("muted danger"). */
export function toneClasses(tags: string | null | undefined): string {
  return (tags ?? "")
    .split(" ")
    .filter(Boolean)
    .map((tag) => `tone-${tag}`)
    .join(" ");
}
