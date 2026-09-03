/**
 * A position inside a recording, written the shortest way that is still
 * unambiguous.
 *
 * Hours appear only when there are any. A two-minute recording read as
 * `0:02:14` is three characters of noise, and this runs down the left edge of
 * a transcript a hundred times over -- but an eighty-four-minute one written
 * as `84:12` is a number nobody can place against a player that says `1:24:12`.
 *
 * `like` is the reading this one has to sit beside, and it fixes the shape:
 * elapsed and total in a player are one string, and `0:00` growing into
 * `1:23:30` as it runs is four characters appearing under the eye. In a flex
 * row that is not just a number changing -- everything beside it moves, and
 * the seek bar sharing the row breathes in and out for the whole recording.
 * Tabular figures do not help, because the count of them is what changes.
 */
export function formatClock(seconds: number, like = seconds): string {
  const whole = Math.max(0, Math.floor(seconds));
  const scale = Math.max(0, Math.floor(like));
  const rest = String(whole % 60).padStart(2, "0");

  if (scale >= 3600) {
    const hours = String(Math.floor(whole / 3600)).padStart(
      String(Math.floor(scale / 3600)).length,
      "0",
    );
    const minutes = String(Math.floor(whole / 60) % 60).padStart(2, "0");
    return `${hours}:${minutes}:${rest}`;
  }

  const minutes = String(Math.floor(whole / 60)).padStart(
    String(Math.floor(scale / 60)).length,
    "0",
  );
  return `${minutes}:${rest}`;
}
