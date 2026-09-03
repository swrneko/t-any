import type { TranscriptSegment } from "@/api/client";

/**
 * What a transcript is made of once it is read rather than replayed.
 *
 * A provider returns one segment per breath -- eighty-four minutes came back as
 * nine hundred and sixty-eight of them -- and nine hundred short lines stacked
 * down a page is a log, not a document. Nothing about that division is
 * meaningful to a reader: it is where the model decided to stop, not where the
 * speaker did. So the lines are gathered back into paragraphs for reading and
 * kept whole underneath, because a correction, a timestamp and a search hit all
 * still belong to the line the provider gave us.
 */
export interface Paragraph {
  /** The first line's own index: unique, stable, and what a React key wants. */
  key: number;
  start: number;
  end: number;
  speaker: string | null;
  lines: TranscriptSegment[];
}

/** Silence longer than this is a break in the talking rather than a breath. */
const BREAK_SECONDS = 1.6;
/** How long a paragraph may run before the next full stop ends it... */
const SOFT_SECONDS = 40;
/** ...and how long it may run when no full stop ever arrives. Somebody reading
 *  a wall of text needs a place to rest their eye even mid-sentence. */
const HARD_SECONDS = 80;

const SENTENCE_END = /[.!?…]["»)\]]?$/;

/** The lines gathered into paragraphs, in the order they were spoken. */
export function intoParagraphs(segments: TranscriptSegment[]): Paragraph[] {
  const paragraphs: Paragraph[] = [];

  for (const line of segments) {
    const open = paragraphs[paragraphs.length - 1];
    if (open && !breaks(open, line)) {
      open.lines.push(line);
      open.end = line.end;
      continue;
    }
    paragraphs.push({
      key: line.idx,
      start: line.start,
      end: line.end,
      speaker: line.speaker,
      lines: [line],
    });
  }

  return paragraphs;
}

/** Three reasons to start a new one, in the order they are worth trusting. */
function breaks(open: Paragraph, line: TranscriptSegment): boolean {
  // Somebody else is talking. Nothing else needs to be considered.
  if (line.speaker !== open.speaker) return true;
  // A pause long enough to hear.
  if (line.start - open.end >= BREAK_SECONDS) return true;

  const running = open.end - open.start;
  if (running >= HARD_SECONDS) return true;
  const said = open.lines[open.lines.length - 1].text.trimEnd();
  return running >= SOFT_SECONDS && SENTENCE_END.test(said);
}

/**
 * A stretch of one voice, with the pauses left as gaps.
 *
 * The timeline draws the whole recording across the width of a page, where nine
 * hundred segments are nine hundred boxes under a pixel wide -- so they are
 * joined into runs first, and what is left is the shape of the conversation:
 * who talked, for how long, and where the silences were.
 */
export interface Run {
  start: number;
  end: number;
  speaker: string | null;
}

/** Below this, a gap is not a silence anybody would look for on a bar. */
const JOIN_SECONDS = 1.0;

export function speakerRuns(segments: TranscriptSegment[]): Run[] {
  const runs: Run[] = [];

  for (const line of segments) {
    const open = runs[runs.length - 1];
    if (open && line.speaker === open.speaker && line.start - open.end < JOIN_SECONDS) {
      open.end = line.end;
      continue;
    }
    runs.push({ start: line.start, end: line.end, speaker: line.speaker });
  }

  return runs;
}

/**
 * Case-insensitive, and blind to the difference between ё and е.
 *
 * Nobody searching a transcript means that distinction, and the provider is not
 * consistent about it either -- the same word comes back both ways inside one
 * recording. Every mapping here is one character to one character, which is
 * what lets an offset found in the folded text be used against the original.
 */
export function fold(text: string): string {
  return text.toLowerCase().replaceAll("ё", "е");
}

/** Which lines hold the query, in the order they are spoken. */
export function linesMatching(segments: TranscriptSegment[], query: string): number[] {
  const needle = fold(query.trim());
  if (!needle) return [];
  return segments.filter((line) => fold(line.text).includes(needle)).map((line) => line.idx);
}

export interface Piece {
  text: string;
  hit: boolean;
}

/** A line cut into what matches and what does not, with the original's own
 *  casing intact -- see `fold` for why the offsets carry across. */
export function highlight(text: string, query: string): Piece[] {
  const needle = fold(query.trim());
  if (!needle) return [{ text, hit: false }];

  const hay = fold(text);
  const pieces: Piece[] = [];
  let at = 0;

  for (let found = hay.indexOf(needle); found !== -1; found = hay.indexOf(needle, at)) {
    if (found > at) pieces.push({ text: text.slice(at, found), hit: false });
    pieces.push({ text: text.slice(found, found + needle.length), hit: true });
    at = found + needle.length;
  }
  if (at < text.length) pieces.push({ text: text.slice(at), hit: false });

  return pieces;
}
