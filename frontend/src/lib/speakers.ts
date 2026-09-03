import type { Speaker } from "@/api/client";

/**
 * Which of the six colours a voice gets.
 *
 * The classes are written out rather than assembled, because Tailwind reads
 * this file as text: `bg-speaker-${n}` is a class that was never generated and
 * so a block with no colour at all. Six, because a seventh voice on one bar is
 * not told apart by its colour anyway -- the names under the timeline are what
 * disambiguate, and the colour is only there to make the shape of the
 * conversation visible at a glance.
 */
export const SPEAKER_FILL = [
  "bg-speaker-1",
  "bg-speaker-2",
  "bg-speaker-3",
  "bg-speaker-4",
  "bg-speaker-5",
  "bg-speaker-6",
] as const;

export const SPEAKER_INK = [
  "text-speaker-1",
  "text-speaker-2",
  "text-speaker-3",
  "text-speaker-4",
  "text-speaker-5",
  "text-speaker-6",
] as const;

/**
 * A label's place in the transcript's own list of speakers, so the colour holds
 * for as long as the speakers do -- renaming one does not repaint the page.
 * Returns -1 for a recording nobody was attributed in.
 */
export function speakerSlot(label: string | null, speakers: Speaker[]): number {
  if (!label) return -1;
  const place = speakers.findIndex((speaker) => speaker.label === label);
  return place < 0 ? -1 : place % SPEAKER_FILL.length;
}
