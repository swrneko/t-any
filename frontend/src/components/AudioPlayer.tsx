import { Pause, Play, Volume1, Volume2, VolumeX } from "lucide-react";
import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { formatClock } from "@/lib/time";
import { cn } from "@/lib/utils";

/** Loudness is a preference, not a property of a recording: set once, it holds
 *  for the next one and for the next session. Silence is one too, and it has to
 *  be stored for a second reason -- these controls are unmounted and mounted
 *  again every time they dock into the app bar, and a state that started at
 *  `false` would unmute the recording on the way. */
const VOLUME_KEY = "player.volume";
const MUTED_KEY = "player.muted";

function storedVolume(): number {
  // Read as text before it is read as a number: `Number(null)` is zero, so a
  // first visit would arrive silent.
  const stored = localStorage.getItem(VOLUME_KEY);
  const value = Number(stored);
  return stored !== null && Number.isFinite(value) && value >= 0 && value <= 1 ? value : 1;
}

/**
 * The recording itself, which draws nothing.
 *
 * Without `controls` the browser's own stylesheet gives it `display: none`, so
 * this is the sound and nothing else. It is mounted by the page rather than by
 * the controls, and that is not tidiness: the controls travel -- a transcript's
 * player sits in the page and then docks into the app bar as you scroll -- and
 * an element that changes parent is one React unmounts and builds again. The
 * browser would drop the buffer, reload the file and start it from zero, in the
 * middle of a sentence. The element stays where it is; only the buttons move.
 */
export function Recording({
  player,
  src,
}: {
  player: RefObject<HTMLAudioElement | null>;
  src: string;
}) {
  return <audio ref={player} preload="metadata" src={src} />;
}

interface AudioPlayerProps {
  /** The element these controls drive, mounted by the page. A transcript seeks
   *  it when a line is clicked, so it has to be reachable from out there too. */
  player: RefObject<HTMLAudioElement | null>;
  onPlayhead?: (seconds: number) => void;
  /** Whether it is running. The transcript follows the playhead only while
   *  something is actually being said -- a page that scrolls itself when
   *  nothing is playing is a page that moves under the eye reading it. */
  onPlaying?: (playing: boolean) => void;
  /** Something better to drag than a plain line. A transcript hands its own
   *  timeline in here rather than standing one underneath: a seek bar and a
   *  map of the recording are the same control, and drawing both was drawing
   *  the position twice, one above the other. Left out, the line comes back --
   *  which is what a share link gets, having no page to put a map on. */
  track?: ReactNode;
  className?: string;
}

/**
 * The recording, on one line.
 *
 * The browser's own control is a black pill three inches wide and fifty pixels
 * tall that belongs to no palette here, and on a page whose whole point is the
 * text underneath it, it was the loudest thing on screen. So the element keeps
 * playing the audio and stops drawing anything: `controls` is gone, which makes
 * it `display: none` by the UA's own stylesheet, and what is drawn instead is a
 * button, a line and a time -- one row the height of a small button, in the
 * app's colours.
 *
 * Nothing here is state of its own that the element does not already hold. The
 * element is asked what it is doing (`play`, `pause`, `timeupdate`) and told
 * what to do; React only mirrors the answers, so a seek from the transcript and
 * a seek from this bar cannot disagree. Which is also what makes these controls
 * safe to move: mounted somewhere else they read the element and are correct
 * immediately, because they never held anything the element did not.
 */
export function AudioPlayer({ player, onPlayhead, onPlaying, track, className }: AudioPlayerProps) {
  const { t } = useTranslation();

  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);
  const [volume, setVolume] = useState(storedVolume);
  const [muted, setMuted] = useState(() => localStorage.getItem(MUTED_KEY) === "true");

  // The page's own handlers are written inline, so they are new functions on
  // every render. Held here, the subscription below does not have to be torn
  // down and rebuilt sixty times a second to stay current.
  const tells = useRef({ onPlayhead, onPlaying });
  tells.current = { onPlayhead, onPlaying };

  useEffect(() => {
    const audio = player.current;
    if (!audio) return;

    const moved = () => {
      setAt(audio.currentTime);
      tells.current.onPlayhead?.(audio.currentTime);
    };
    // A stream of unknown length reports Infinity, and a slider with an
    // infinite maximum has no position to draw.
    const measured = () => setLength(Number.isFinite(audio.duration) ? audio.duration : 0);
    const answered = () => {
      setPlaying(!audio.paused);
      tells.current.onPlaying?.(!audio.paused);
    };

    audio.addEventListener("timeupdate", moved);
    audio.addEventListener("loadedmetadata", measured);
    audio.addEventListener("durationchange", measured);
    audio.addEventListener("play", answered);
    audio.addEventListener("pause", answered);
    audio.addEventListener("ended", answered);

    // Mounted onto an element that has been playing for a while -- which is
    // what docking is -- so start from where it already is rather than from
    // zero, before a single event has had a chance to say so.
    measured();
    setAt(audio.currentTime);
    setPlaying(!audio.paused);

    return () => {
      audio.removeEventListener("timeupdate", moved);
      audio.removeEventListener("loadedmetadata", measured);
      audio.removeEventListener("durationchange", measured);
      audio.removeEventListener("play", answered);
      audio.removeEventListener("pause", answered);
      audio.removeEventListener("ended", answered);
    };
  }, [player]);

  useEffect(() => {
    if (!player.current) return;
    player.current.volume = volume;
    player.current.muted = muted;
  }, [player, volume, muted]);

  // `timeupdate` fires about four times a second, which is a handle that hops
  // rather than travels. While something is playing the position is read once
  // per frame instead, from the element's own clock -- so the movement is the
  // browser's, not an animation guessing at it, and it stays right through a
  // seek, a pause and a rate change. The page above is still told only on
  // `timeupdate`: which line is being spoken cannot change sixty times a
  // second, and re-rendering a transcript that often would cost more than the
  // smoothness is worth.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const follow = () => {
      if (player.current) setAt(player.current.currentTime);
      frame = requestAnimationFrame(follow);
    };
    frame = requestAnimationFrame(follow);
    return () => cancelAnimationFrame(frame);
  }, [playing, player]);

  const changeVolume = (next: number) => {
    localStorage.setItem(VOLUME_KEY, String(next));
    setVolume(next);
    // Dragging the volume up is the plainest way to say "let me hear it".
    if (next > 0) silence(false);
  };

  const silence = (next: boolean) => {
    localStorage.setItem(MUTED_KEY, String(next));
    setMuted(next);
  };

  const seek = (seconds: number) => {
    if (!player.current) return;
    player.current.currentTime = seconds;
    // `timeupdate` follows a seek, but not before the next frame; setting it
    // here keeps the handle under the finger that dragged it.
    setAt(seconds);
    onPlayhead?.(seconds);
  };

  const Loud = muted || volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;

  return (
    // A pill, like everything else on this page that is a control rather than a
    // reading: the play button rides in the rounded end it fits, and the row is
    // one object instead of four loose ones laid on the background.
    <div
      className={cn(
        "flex items-center gap-3 rounded-full border border-border bg-card py-1.5 pr-4 pl-1.5",
        className,
      )}
    >
      <Button
        size="icon-sm"
        aria-label={t(playing ? "player.pause" : "player.play")}
        onClick={() => {
          if (!player.current) return;
          if (playing) player.current.pause();
          else void player.current.play();
        }}
      >
        {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </Button>

      {track ?? (
        <Slider
          className="flex-1"
          value={[Math.min(at, length)]}
          max={length || 1}
          step={0.01}
          aria-label={t("player.seek")}
          aria-valuetext={formatClock(at)}
          onValueChange={([seconds]) => seek(seconds)}
        />
      )}

      {/* One reading, not two: elapsed and total are the same size beside each
          other, and tabular figures keep the line from twitching every second.
          Elapsed is written in the total's shape as well, so the string is the
          same length at every position -- otherwise the seek bar sharing this
          row is squeezed and let out again every time the clock crosses ten
          minutes or an hour, which is most of what a drag looks like. */}
      <span className="font-mono text-xs tabular-nums text-muted-foreground">
        {formatClock(at, length)} / {formatClock(length)}
      </span>

      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t(muted ? "player.unmute" : "player.mute")}
        onClick={() => silence(!muted)}
      >
        <Loud className="size-4" />
      </Button>

      {/* The narrow screen keeps the phone's own volume keys and loses this. */}
      <Slider
        className="hidden w-16 sm:flex"
        value={[muted ? 0 : volume]}
        max={1}
        step={0.01}
        aria-label={t("player.volume")}
        onValueChange={([next]) => changeVolume(next)}
      />
    </div>
  );
}
