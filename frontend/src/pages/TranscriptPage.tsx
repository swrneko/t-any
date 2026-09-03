import { ArrowLeft, Copy, Loader2, LocateFixed, Pencil, Users } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type Job, type Speaker, type Transcript, type TranscriptSegment } from "@/api/client";
import { useBarSlot } from "@/components/AppShell";
import { AudioPlayer, Recording } from "@/components/AudioPlayer";
import { ExportMenu } from "@/components/ExportMenu";
import { MorphLink } from "@/components/MorphLink";
import { ShareDialog } from "@/components/ShareDialog";
import { SummaryPanel } from "@/components/SummaryPanel";
import { TranscriptSearch } from "@/components/TranscriptSearch";
import { TranscriptTimeline } from "@/components/TranscriptTimeline";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { displayLanguage } from "@/lib/language";
import { highlight, intoParagraphs, linesMatching } from "@/lib/paragraphs";
import { SPEAKER_FILL, SPEAKER_INK, speakerSlot } from "@/lib/speakers";
import { formatClock } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useApiErrorMessage, useCodeMessage } from "@/useApiError";
import { isPending } from "@/useJobFeed";

/** One array, so a transcript that has not arrived does not hand a new empty
 *  one to every memo on every render. */
const NOTHING: TranscriptSegment[] = [];

/** Keys that move the page. Pressing one means the reader has taken over, the
 *  same as turning a wheel does. */
const SCROLLS = new Set(["PageUp", "PageDown", "ArrowUp", "ArrowDown", "Home", "End", " "]);

/** The app bar's underside once the page has moved: twelve pixels of gutter and
 *  fifty-six of glass. Where the controls go when they dock. */
const BAR_BOTTOM = 68;

/**
 * Where the controls are standing.
 *
 * `page` is where they belong -- under the title, over the words they act on.
 * `bar` is where they go once the page has carried them up to it, and there
 * they are the bar rather than a panel under it. `footer` is where they end:
 * once the last line of the transcript has reached the bar there is nothing
 * left for them to hover over, so they settle onto the bottom of the block
 * they were reading and scroll away with it.
 */
type Place = "page" | "bar" | "footer";

export function TranscriptPage() {
  const { jobId = "" } = useParams();
  const [params] = useSearchParams();
  const { t, i18n } = useTranslation();
  const describe = useApiErrorMessage();
  const player = useRef<HTMLAudioElement>(null);
  const slot = useBarSlot();

  const [job, setJob] = useState<Job | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [copied, setCopied] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [hasDiarizer, setHasDiarizer] = useState(false);
  const [query, setQuery] = useState("");
  const [hit, setHit] = useState(0);
  const [following, setFollowing] = useState(true);
  // Where the controls are standing, and how much room to hold open where they
  // rest so the page does not jump when they leave it.
  const [place, setPlace] = useState<Place>("page");
  const [reserve, setReserve] = useState(0);
  const mark = useRef<HTMLDivElement>(null);
  const tail = useRef<HTMLDivElement>(null);
  // Whether this arrival is a move or a first appearance. Only a move is worth
  // animating: a transcript opened straight onto a scrolled position would
  // otherwise play the docking as though it had just happened.
  const stood = useRef<Place | null>(null);
  const [moved, setMoved] = useState(false);
  const docked = place === "bar";
  const navigate = useNavigate();

  // Where each line ended up on screen. A map rather than a query selector: the
  // three things that scroll this page -- the playhead, a search hit and the
  // moment a link pointed at -- all name a line by its index, not by a class.
  const lines = useRef(new Map<number, HTMLElement>());

  // This frame used to carry a view-transition name, so that the row it was
  // opened from grew into it. It does not any more: the box such a name travels
  // on runs from the height of a list row to the height of a page, and an
  // engine is free to stretch the captured picture into that box -- which is
  // the page arriving squashed and unfolding, the oldest complaint in this
  // file. The page arrives the way every other screen does, with `page-in`.

  useEffect(() => {
    void api.setupStatus().then((status) => setHasDiarizer(status.has_diarizer));
  }, []);

  // The job first, on its own: a recording queued a second ago has no
  // transcript, and asking for one would turn "still working" into an error.
  useEffect(() => {
    setJob(null);
    setTranscript(null);
    api
      .readJob(jobId)
      .then(setJob)
      .catch((cause: unknown) => setError(describe(cause)));
    // describe is rebuilt on every language change; refetching then is waste.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const working = job !== null && isPending(job);
  useEffect(() => {
    if (!working) return;
    return api.watchJob(jobId, setJob);
  }, [jobId, working]);

  useEffect(() => {
    if (job?.status !== "done" || transcript) return;
    api
      .readTranscript(jobId)
      .then(setTranscript)
      .catch((cause: unknown) => setError(describe(cause)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, job?.status]);

  const segments = transcript?.segments ?? NOTHING;
  const paragraphs = useMemo(() => intoParagraphs(segments), [segments]);
  const matches = useMemo(() => linesMatching(segments, query), [segments, query]);

  const current = segments.find((line) => playhead >= line.start && playhead < line.end);
  const currentIdx = current?.idx;
  const spot = matches.length === 0 ? -1 : Math.min(hit, matches.length - 1);
  const aimed = spot < 0 ? undefined : matches[spot];

  const show = (idx: number) =>
    lines.current.get(idx)?.scrollIntoView({ block: "center", behavior: "smooth" });

  // A search result links to the moment it found, not just to the recording,
  // and a moment an hour in is four hundred lines down the page.
  const at = Number(params.get("at") ?? Number.NaN);
  useEffect(() => {
    if (!transcript || Number.isNaN(at) || !player.current) return;
    player.current.currentTime = at;
    setPlayhead(at);
    const line = transcript.segments.find((one) => at >= one.start && at < one.end);
    if (!line) return;
    // A frame later, because the lines register themselves as they are drawn
    // and this runs with the page still empty.
    const frame = requestAnimationFrame(() =>
      lines.current.get(line.idx)?.scrollIntoView({ block: "center" }),
    );
    return () => cancelAnimationFrame(frame);
  }, [transcript, at]);

  // Asking a different question starts the answers again from the top.
  useEffect(() => setHit(0), [query]);

  useEffect(() => {
    if (aimed === undefined) return;
    // Reading by text and following the audio are two different intentions, and
    // the page cannot be doing both.
    setFollowing(false);
    show(aimed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aimed]);

  // The transcript keeps up with the recording, but only while it is running:
  // a page that scrolls itself when nothing is playing is a page moving under
  // the eye that is reading it.
  useEffect(() => {
    if (!following || !playing || currentIdx === undefined) return;
    show(currentIdx);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [following, playing, currentIdx]);

  // Two hairlines -- one where the controls rest, one at the last line of the
  // transcript -- read against the bar's underside on every scroll.
  //
  // A listener rather than an IntersectionObserver, which is what this was: an
  // observer answers at the end of a frame rather than during the scroll, and
  // the third position has no `sticky` standing in for it the way the second
  // does. On a wheel step of a hundred pixels the answer would arrive with the
  // panel already that far past where it was meant to stop. Neither mark moves
  // when the controls arrive or leave -- the room they take is either held open
  // or added below the mark -- so there is no boundary to flap across.
  useEffect(() => {
    if (!transcript) return;

    const look = () => {
      const top = mark.current?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY;
      const end = tail.current?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY;
      const next: Place = end <= BAR_BOTTOM ? "footer" : top <= BAR_BOTTOM ? "bar" : "page";
      if (stood.current !== null && stood.current !== next) setMoved(true);
      stood.current = next;
      setPlace(next);
    };

    look();
    window.addEventListener("scroll", look, { passive: true });
    window.addEventListener("resize", look);
    return () => {
      window.removeEventListener("scroll", look);
      window.removeEventListener("resize", look);
    };
  }, [transcript]);

  // Measured wherever it currently is, since it is the same block either way.
  const measure = useCallback((node: HTMLDivElement | null) => {
    if (!node) return undefined;
    const watch = new ResizeObserver(() => setReserve(node.offsetHeight));
    watch.observe(node);
    return () => watch.disconnect();
  }, []);

  // Scrolling by hand is how you say "let me read somewhere else". Nothing here
  // listens to `scroll`, because the scrolling this page does itself would then
  // switch itself off on its first frame.
  useEffect(() => {
    const stop = () => setFollowing(false);
    const byKey = (event: KeyboardEvent) => {
      const from = event.target as HTMLElement | null;
      if (from && (from.tagName === "INPUT" || from.tagName === "TEXTAREA")) return;
      if (SCROLLS.has(event.key)) setFollowing(false);
    };
    window.addEventListener("wheel", stop, { passive: true });
    window.addEventListener("touchmove", stop, { passive: true });
    window.addEventListener("keydown", byKey);
    return () => {
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchmove", stop);
      window.removeEventListener("keydown", byKey);
    };
  }, []);

  /** The job goes back in the queue, which is the page that answers for it. */
  const askForSpeakers = async () => {
    try {
      await api.diarizeJob(jobId);
      navigate("/");
    } catch (cause: unknown) {
      setError(describe(cause));
    }
  };

  const seek = (seconds: number, andPlay = false) => {
    if (!player.current) return;
    player.current.currentTime = seconds;
    setPlayhead(seconds);
    if (andPlay) void player.current.play();
  };

  const step = (delta: number) => {
    if (matches.length === 0) return;
    setHit(
      (from) => (Math.min(from, matches.length - 1) + delta + matches.length) % matches.length,
    );
  };

  const copy = async () => {
    if (!transcript) return;
    await navigator.clipboard.writeText(transcript.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (error) {
    return (
      <div className="grid gap-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  // Not a spinner: this is the shape the recording is about to take, so the
  // page does not jump once it knows what it holds.
  if (!job) {
    return (
      <div className="grid gap-4">
        <BackLink />
        <Card className="gap-4 p-6">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </Card>
      </div>
    );
  }

  // Opened the moment the upload finished, so the recording is usually still
  // being worked on. The same address answers for both halves of its life.
  if (!transcript) {
    return (
      <div className="grid gap-4">
        <BackLink />
        <JobProgress job={job} onCancel={() => void api.cancelJob(job.id).then(setJob)} />
      </div>
    );
  }

  const nameOf = (label: string) =>
    transcript.speakers.find((speaker) => speaker.label === label)?.display_name ?? label;

  const correct = async (segment: TranscriptSegment) => {
    setEditing(null);
    if (draft.trim() === segment.text.trim()) return;
    const saved = await api.correctSegment(job.id, segment.idx, draft);
    const kept = transcript.segments.map((one) => (one.idx === saved.idx ? saved : one));
    // `text` is derived, so it has to be re-derived: it is what the copy
    // button copies, and it would otherwise still hold the old wording.
    setTranscript({
      ...transcript,
      segments: kept,
      text: kept
        .map((one) => one.text)
        .join(" ")
        .trim(),
    });
  };

  // An hour of recording puts an hour on every timestamp, and `1:04:12` does
  // not fit the column `4:12` was measured for.
  const gutter = (job.duration_sec ?? 0) >= 3600 ? "min-w-[4.25rem]" : "min-w-14";
  const offering = hasDiarizer && job.audio_bytes !== null && transcript.speakers.length === 0;

  /**
   * Everything that acts on the recording: playing it, finding a word in it,
   * seeing where you are in it and getting it off the page.
   *
   * One element, rendered in one of two places. It starts where it belongs --
   * under the title, over the words it acts on -- and once the page has carried
   * it up to the app bar it is rendered inside the bar's island instead, where
   * it is the bar: one glass, one edge, one shadow. Sticking it to the bar's
   * underside was the near miss; two surfaces a pixel apart are two surfaces
   * however carefully they are aligned, and being one thing is not something
   * alignment can achieve.
   *
   * Which is why the audio element is not in here (see `Recording`): moving
   * this between parents is a full unmount, and the sound would stop every
   * time you scrolled past the title.
   */
  const controls = (
    <div
      // Measured only where it rests, because what is being held open is the
      // room it had there. Docked it is three pixels shorter -- it gives up a
      // border and takes the bar's padding -- and reserving that instead would
      // pull the whole transcript up by three the moment it left.
      ref={place === "page" ? measure : undefined}
      className={cn(
        "grid gap-2.5 px-3",
        // No shadow at rest, and that is for the joint rather than for taste:
        // a five-layer glass shadow has no matching shape to interpolate
        // towards, so it can only snap on and off. Corners and fill are two
        // properties that do interpolate, and they are the whole of the
        // difference between resting and docked.
        place === "page" && "rounded-[1.75rem] border border-border bg-card py-2.5",
        // In the bar and in the card's footer it is the same thing: a division
        // of a surface it is already inside, so all it draws is the rule above
        // it, in whichever hairline that surface uses.
        place === "bar" && "border-t border-glass-edge pt-2 pb-2.5",
        place === "footer" && "border-t border-border pt-2 pb-2.5",
        moved && (place === "page" ? "animate-undock" : place === "bar" ? "animate-dock" : null),
      )}
    >
      {job.audio_bytes !== null && (
        <AudioPlayer
          player={player}
          onPlayhead={setPlayhead}
          onPlaying={setPlaying}
          track={
            <TranscriptTimeline
              className="flex-1"
              segments={transcript.segments}
              speakers={transcript.speakers}
              length={job.duration_sec ?? 0}
              at={playhead}
              onSeek={(seconds) => seek(seconds)}
              player={player}
            />
          }
        />
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <TranscriptSearch
          className="min-w-52 flex-1"
          query={query}
          onQuery={setQuery}
          found={matches.length}
          at={spot < 0 ? 0 : spot}
          onStep={step}
        />

        <div className="flex items-center gap-2">
          {job.audio_bytes !== null && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={following ? "default" : "outline"}
                  size="icon-sm"
                  aria-pressed={following}
                  aria-label={t("transcript.follow")}
                  onClick={() => {
                    if (following) {
                      setFollowing(false);
                      return;
                    }
                    setFollowing(true);
                    if (currentIdx !== undefined) show(currentIdx);
                  }}
                >
                  <LocateFixed className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("transcript.followHint")}</TooltipContent>
            </Tooltip>
          )}

          <Label htmlFor="timestamps" className="text-sm text-muted-foreground">
            {t("transcript.timestamps")}
          </Label>
          <Switch
            id="timestamps"
            size="sm"
            checked={showTimestamps}
            onCheckedChange={setShowTimestamps}
          />
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void copy()}>
            <Copy className="size-4" />
            {copied ? t("transcript.copied") : t("transcript.copy")}
          </Button>
          <ExportMenu
            urlFor={(format, options) => api.exportUrl(job.id, format, options)}
            readText={(format, options) => api.readExport(job.id, format, options)}
          />
          <ShareDialog jobId={job.id} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="grid gap-6">
      <BackLink />

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>
        {transcript.language && (
          <p className="text-sm text-muted-foreground">
            {t("transcript.language", {
              language: displayLanguage(transcript.language, i18n.language),
            })}
          </p>
        )}
      </div>

      {/* A player with nothing to play reads as a broken page, so the recording
          having been freed is said in words instead. */}
      {job.audio_bytes === null && (
        <p className="text-sm text-muted-foreground">{t("transcript.audioGone")}</p>
      )}

      {/* The sound, mounted once and never moved. */}
      {job.audio_bytes !== null && <Recording player={player} src={api.audioUrl(job.id)} />}

      {docked && slot && createPortal(controls, slot)}

      {/* The controls and the words they act on, in one tall box -- tall being
          the point of it, since it is what the panel sticks inside while it is
          on its way to the bar.

          Position is `sticky`'s job and not the listener's. Stuck, the panel
          parks against the bar's underside on the browser's own clock, frame
          for frame, so by the time the listener speaks it is already standing
          exactly where the bar will draw it and the move has nothing left to do
          but the material.

          The mark is absolute so that it costs no row of its own and, more to
          the point, so that it keeps scrolling after the panel has stopped: a
          stuck element's top never changes again, and a mark inside one would
          never report anything. The room the panel took is held open while it
          is away, or the transcript would jump up by its height. */}
      <div className="relative grid gap-6">
        <div ref={mark} aria-hidden className="absolute inset-x-0 top-0 h-0" />

        <div
          className={cn(place === "page" && "sticky top-17 z-10")}
          style={place === "page" ? undefined : { height: reserve }}
        >
          {place === "page" && controls}
        </div>

        <Card className="gap-0 overflow-hidden p-0">
          {/* Who was talking is about the recording rather than about reading it,
            and it is asked once. So it sits under the bar and scrolls away with
            the words, instead of taking a line of the one thing that stays. */}
          {(offering || transcript.speakers.length > 0) && (
            <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-2.5">
              {/* Offered only when there is nothing to lose: a recording still on
                disk, nobody attributed yet, and a diariser to ask. Wanting
                speakers after reading the transcript is the normal way round,
                and it used to mean handing the whole recording in a second
                time. What that costs is a sentence long, so it is a tooltip
                rather than a line of prose in a row of controls. */}
              {offering && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="outline" size="sm" onClick={() => void askForSpeakers()}>
                      <Users className="size-4" />
                      {t("transcript.diarize")}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t("transcript.diarizeHint")}</TooltipContent>
                </Tooltip>
              )}

              {transcript.speakers.length > 0 && (
                <SpeakerBar
                  speakers={transcript.speakers}
                  onRename={(id, name) =>
                    void api.renameSpeaker(job.id, id, name).then((saved) =>
                      setTranscript({
                        ...transcript,
                        speakers: transcript.speakers.map((one) =>
                          one.id === saved.id ? saved : one,
                        ),
                      }),
                    )
                  }
                />
              )}
            </div>
          )}

          {/* Paragraphs, not lines. What the provider returns is one segment per
            breath, and stacking nine hundred of them down a page makes a log
            out of a document -- the divisions are where the model stopped, not
            where anybody did. The lines are still there underneath: a click
            still seeks to the one under the cursor, a correction still belongs
            to one of them, and a search hit still names one. */}
          <div className="grid gap-4 p-4">
            {paragraphs.map((paragraph, index) => {
              const slot = speakerSlot(paragraph.speaker, transcript.speakers);
              // Named once per turn, not once per paragraph: a name repeated over
              // every block is what makes a diarised transcript unreadable.
              const speaks =
                paragraph.speaker && paragraph.speaker !== paragraphs[index - 1]?.speaker
                  ? nameOf(paragraph.speaker)
                  : null;

              return (
                <Fragment key={paragraph.key}>
                  {/* Over the words rather than over the clock: a name standing
                    above the timestamp column belongs to the timestamp. */}
                  {speaks && (
                    <div className="-mb-2.5 flex gap-3">
                      {showTimestamps && <span aria-hidden className={cn("shrink-0", gutter)} />}
                      <p
                        className={cn(
                          "text-sm font-semibold",
                          slot < 0 ? "text-primary" : SPEAKER_INK[slot],
                        )}
                      >
                        {speaks}
                      </p>
                    </div>
                  )}

                  <div className="flex gap-3">
                    {/* The one focusable thing per paragraph, so the whole
                      transcript is not nine hundred tab stops. */}
                    {showTimestamps && (
                      <button
                        type="button"
                        onClick={() => seek(paragraph.start)}
                        className={cn(
                          "h-fit shrink-0 rounded-md pt-0.5 text-left font-mono text-sm tabular-nums",
                          "text-muted-foreground outline-none transition-colors hover:text-foreground",
                          "focus-visible:ring-[3px] focus-visible:ring-ring/50",
                          gutter,
                        )}
                      >
                        {formatClock(paragraph.start)}
                      </button>
                    )}

                    <p className="flex-1 leading-relaxed">
                      {paragraph.lines.map((line) =>
                        editing === line.idx ? (
                          <Textarea
                            key={line.idx}
                            autoFocus
                            rows={2}
                            value={draft}
                            className="my-1"
                            aria-label={t("transcript.correct")}
                            onChange={(event) => setDraft(event.target.value)}
                            onBlur={() => void correct(line)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                event.currentTarget.blur();
                              }
                              // Escape puts the text back, and the equality check
                              // in `correct` turns the blur that follows into
                              // nothing.
                              if (event.key === "Escape") {
                                setDraft(line.text);
                                setEditing(null);
                              }
                            }}
                          />
                        ) : (
                          <Fragment key={line.idx}>
                            <span
                              ref={(node) => {
                                if (node) lines.current.set(line.idx, node);
                                else lines.current.delete(line.idx);
                              }}
                              title={t(
                                line.edited ? "transcript.corrected" : "transcript.lineHint",
                              )}
                              // One click seeks, which is what a transcript beside
                              // a player is for. Correcting is the second click,
                              // and it stops the audio -- fixing a line while it
                              // is being read out is two things at once.
                              onClick={() => seek(line.start, true)}
                              onDoubleClick={() => {
                                player.current?.pause();
                                setDraft(line.text);
                                setEditing(line.idx);
                              }}
                              className={cn(
                                "cursor-pointer rounded-sm transition-colors hover:bg-accent/60",
                                line.idx === currentIdx && "bg-accent font-medium",
                                line.edited && "italic",
                              )}
                            >
                              {highlight(line.text, query).map((piece, part) =>
                                piece.hit ? (
                                  <mark
                                    key={part}
                                    className={cn(
                                      "rounded-[3px] text-inherit",
                                      line.idx === aimed ? "bg-warning/55" : "bg-warning/25",
                                    )}
                                  >
                                    {piece.text}
                                  </mark>
                                ) : (
                                  <Fragment key={part}>{piece.text}</Fragment>
                                ),
                              )}
                            </span>{" "}
                          </Fragment>
                        ),
                      )}
                    </p>
                  </div>
                </Fragment>
              );
            })}
          </div>

          {/* The last line, and what the controls settle onto once it has gone
              under the bar. There is nothing left for them to hover over at
              that point -- the block they belong to is behind you -- so they
              stop hovering and become its footer, and scroll away with it.

              The mark is above the footer rather than below it, so landing does
              not move the thing that decided to land: the room the controls take
              is added underneath it, which is why this boundary cannot flap. */}
          <div ref={tail} aria-hidden className="h-0" />
          {place === "footer" && controls}
        </Card>
      </div>

      <SummaryPanel jobId={job.id} />
    </div>
  );
}

/** The recording as it is being made: what is happening to it, how far that has
 *  got, and the one button that stops it. */
function JobProgress({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const { t } = useTranslation();
  const describeCode = useCodeMessage();

  return (
    <Card className="gap-4 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>

      {job.status === "failed" ? (
        <Alert variant="destructive">
          <AlertDescription>{describeCode(job.error_code, job.error_params)}</AlertDescription>
        </Alert>
      ) : job.status === "cancelled" ? (
        <p className="text-sm text-muted-foreground">{t("jobs.status.cancelled")}</p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {job.stage ? t(`jobs.stage.${job.stage}`) : t(`jobs.status.${job.status}`)}
            </span>
          </div>
          <Progress value={job.progress * 100} indeterminate={job.progress === 0} />
          <p className="text-sm text-muted-foreground">{t("transcript.working")}</p>
          {job.status !== "cancelling" && (
            <Button variant="outline" size="sm" className="justify-self-start" onClick={onCancel}>
              {t("jobs.cancel")}
            </Button>
          )}
        </>
      )}
    </Card>
  );
}

function SpeakerBar({
  speakers,
  onRename,
}: {
  speakers: Speaker[];
  onRename: (id: string, displayName: string) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-muted-foreground">{t("transcript.speakers")}</span>
      {speakers.map((speaker, index) =>
        editing === speaker.id ? (
          <Input
            key={speaker.id}
            autoFocus
            value={draft}
            className="h-8 w-40"
            placeholder={speaker.label}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => {
              setEditing(null);
              if (draft.trim() !== (speaker.display_name ?? "")) onRename(speaker.id, draft);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
              // Escape leaves the name as it was: a rename typed into the wrong
              // speaker has to be abandonable.
              if (event.key === "Escape") {
                setDraft(speaker.display_name ?? "");
                setEditing(null);
              }
            }}
          />
        ) : (
          <Button
            key={speaker.id}
            variant="outline"
            size="sm"
            title={t("transcript.rename")}
            onClick={() => {
              setDraft(speaker.display_name ?? "");
              setEditing(speaker.id);
            }}
          >
            {/* The same colour this voice has on the timeline, so the bar above
                can be read without a legend of its own. */}
            <span
              aria-hidden
              className={cn("size-2 rounded-full", SPEAKER_FILL[index % SPEAKER_FILL.length])}
            />
            {speaker.display_name ?? speaker.label}
            <Pencil className="size-3 text-muted-foreground" />
          </Button>
        ),
      )}
    </div>
  );
}

function BackLink() {
  const { t } = useTranslation();
  return (
    // Outlined rather than bare: with no edge it read as the page's first line
    // of text that happens to carry an arrow, and the one control that leaves
    // the screen should look like a control.
    <Button asChild variant="outline" size="sm" className="justify-self-start">
      {/* Back to where transcripts live, which is the archive rather than the
          upload screen this one may have been opened from. */}
      <MorphLink to="/history">
        <ArrowLeft className="size-4" />
        {t("transcript.back")}
      </MorphLink>
    </Button>
  );
}
