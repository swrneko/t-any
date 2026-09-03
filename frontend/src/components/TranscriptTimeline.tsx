import { type PointerEvent, type RefObject, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { Speaker, TranscriptSegment } from "@/api/client";
import { speakerRuns, type Run } from "@/lib/paragraphs";
import { SPEAKER_FILL, speakerSlot } from "@/lib/speakers";
import { formatClock } from "@/lib/time";
import { cn } from "@/lib/utils";

interface TranscriptTimelineProps {
  segments: TranscriptSegment[];
  speakers: Speaker[];
  /** How long the recording is. The last segment's end is close but not equal:
   *  a recording usually stops a few seconds after the last word. */
  length: number;
  at: number;
  onSeek: (seconds: number) => void;
  /** The element itself, so the marker can follow its clock rather than the
   *  page's. `timeupdate` arrives four times a second, which is a marker that
   *  hops; read once a frame it travels. Nothing re-renders for it -- the
   *  position is written straight onto the marker, so sixty frames a second
   *  cost nothing above the fifty blocks already drawn. */
  player?: RefObject<HTMLAudioElement | null>;
  className?: string;
}

/** How far the playhead moves on one press of an arrow key. Long enough to
 *  cross a paragraph, short enough to land inside a sentence again. */
const STEP_SECONDS = 15;

/** The shortest silence worth a gap on a short recording, where a second is
 *  wide enough to see. On a long one the width decides instead. */
const JOIN_SECONDS = 1.0;

/** Candidate spacings for the scale, coarsest last. The first that leaves no
 *  more than eight labels wins, so a two-minute recording is marked in
 *  half-minutes and a two-hour one in quarter-hours. */
const TICKS = [15, 30, 60, 120, 300, 600, 900, 1800, 3600];

/**
 * The recording as one bar: who spoke, when, where the silences are, and where
 * you have got to.
 *
 * It is the player's seek bar as well, and that is the point of it. A line
 * showing position and a map showing shape are the same control asked two
 * questions, and drawing both -- one directly above the other, the same
 * playhead on each -- was the position stated twice. So the player hands its
 * track over to this and keeps the button, the clock and the volume.
 */
export function TranscriptTimeline({
  segments,
  speakers,
  length,
  at,
  onSeek,
  player,
  className,
}: TranscriptTimelineProps) {
  const { t } = useTranslation();
  const marker = useRef<HTMLSpanElement>(null);

  // Nine hundred segments would be nine hundred boxes a third of a pixel wide.
  const runs = useMemo(() => speakerRuns(segments), [segments]);
  const span = length > 0 ? length : (runs[runs.length - 1]?.end ?? 0);
  // And a silence has to be wide enough to be seen before it is worth drawing.
  // An hour and a half across six hundred pixels is eight seconds to the pixel:
  // every ordinary pause between two sentences comes out sub-pixel, and two
  // hundred blocks each rounded up to something visible is not a conversation,
  // it is a barcode. What is left after joining those is the shape that was
  // wanted -- who talked, and where the real gaps are.
  const drawn = useMemo(() => join(runs, Math.max(JOIN_SECONDS, span / 400)), [runs, span]);
  const ticks = useMemo(() => scale(span), [span]);

  useEffect(() => {
    const audio = player?.current;
    if (!audio || span <= 0) return;

    let frame = 0;
    const follow = () => {
      if (marker.current) {
        marker.current.style.left = `${Math.min(100, Math.max(0, (audio.currentTime / span) * 100))}%`;
      }
      frame = requestAnimationFrame(follow);
    };
    const start = () => {
      if (!frame) frame = requestAnimationFrame(follow);
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
    };

    audio.addEventListener("play", start);
    audio.addEventListener("pause", stop);
    audio.addEventListener("ended", stop);
    if (!audio.paused) start();

    return () => {
      stop();
      audio.removeEventListener("play", start);
      audio.removeEventListener("pause", stop);
      audio.removeEventListener("ended", stop);
    };
  }, [player, span]);

  if (span <= 0) return null;

  const across = (seconds: number) => `${Math.min(100, Math.max(0, (seconds / span) * 100))}%`;

  const scrub = (event: PointerEvent<HTMLButtonElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    onSeek(Math.min(span, Math.max(0, ((event.clientX - box.left) / box.width) * span)));
  };

  return (
    // The scale hangs below the bar, and the bar is what everything beside it
    // in the player -- the button, the clock, the volume -- is lined up with.
    // So the same height is left empty above, and the whole column's middle is
    // the bar's middle. Centring the column instead put the bar high and the
    // play button between the two of them, which is what it looked like.
    <div className={cn("grid min-w-0 gap-0.5 pt-3.5", className)}>
      {/* The pill is the frame, and the recording is the straight part inside
          it. A round end eats the first and last twelve pixels of a bar this
          tall -- the beginning and the end of the recording, the two places on
          it anybody can name -- so the working area is a rectangle held clear
          of both corners by exactly their radius, and what curves is the dead
          margin either side of it. The click arithmetic needs nothing said
          about that: it measures the element it is on, which is now the
          rectangle. */}
      <div className="relative h-6 overflow-hidden rounded-full border border-border bg-muted px-3 has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50">
        <button
          type="button"
          aria-label={t("transcript.timeline")}
          className="relative block h-full w-full touch-none outline-none"
          // Captured on the way down, so a drag that leaves the bar keeps
          // scrubbing and one that ends outside it still ends.
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            scrub(event);
          }}
          onPointerMove={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) scrub(event);
          }}
          onKeyDown={(event) => {
            const step =
              event.key === "ArrowRight"
                ? STEP_SECONDS
                : event.key === "ArrowLeft"
                  ? -STEP_SECONDS
                  : 0;
            if (step) {
              event.preventDefault();
              onSeek(Math.min(span, Math.max(0, at + step)));
            }
            if (event.key === "Home") onSeek(0);
            if (event.key === "End") onSeek(span);
          }}
        >
          {drawn.map((run) => {
            const slot = speakerSlot(run.speaker, speakers);
            return (
              <span
                key={run.start}
                aria-hidden
                className={cn(
                  "absolute inset-y-1 rounded-full",
                  // Nobody was attributed, so the bar says only where the talking
                  // is -- which on a recording with long silences is most of what
                  // it was wanted for anyway.
                  slot < 0 ? "bg-primary/60" : SPEAKER_FILL[slot],
                )}
                style={{ left: across(run.start), width: across(run.end - run.start), minWidth: 2 }}
              />
            );
          })}

          {ticks.map((tick) => (
            <span
              key={tick}
              aria-hidden
              className="absolute inset-y-0 w-px bg-border"
              style={{ left: across(tick) }}
            />
          ))}

          {/* At either end half of it hangs over the dead margin, which is what
              that margin is for: the position stays exact and nothing is
              clipped, because the pill's corners are no longer anywhere near
              the working area. */}
          <span
            ref={marker}
            aria-hidden
            className="absolute inset-y-0 w-0.5 -translate-x-1/2 rounded-full bg-foreground"
            style={{ left: across(at) }}
          />
        </button>
      </div>

      {/* The scale, under the bar rather than on it: a number written over a
          block of colour is a number nobody can read at this size. Held in by
          the same margin as the working area, since a label has to stand over
          the tick it names. */}
      <div aria-hidden className="relative mx-3 h-3">
        {ticks.map((tick) => (
          <span
            key={tick}
            className="absolute -translate-x-1/2 font-mono text-[0.6rem]/3 tabular-nums text-muted-foreground"
            style={{ left: across(tick) }}
          >
            {formatClock(tick)}
          </span>
        ))}
      </div>
    </div>
  );
}

/** The same voice either side of a gap nobody could see. */
function join(runs: Run[], gap: number): Run[] {
  const joined: Run[] = [];
  for (const run of runs) {
    const open = joined[joined.length - 1];
    if (open && run.speaker === open.speaker && run.start - open.end < gap) {
      open.end = run.end;
      continue;
    }
    joined.push({ ...run });
  }
  return joined;
}

/** Where the marks go. Neither end is marked: zero and the full length are the
 *  two positions the bar's own edges already state, and a label centred on
 *  either one is half outside the page. */
function scale(span: number): number[] {
  if (span <= 0) return [];
  const step = TICKS.find((candidate) => span / candidate <= 8) ?? TICKS[TICKS.length - 1];
  const marks: number[] = [];
  for (let mark = step; mark < span; mark += step) marks.push(mark);
  return marks;
}
