import { ArrowRight, ChevronDown, ChevronUp, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, type Job } from "@/api/client";
import { formatBytes, JobList } from "@/components/JobList";
import { MorphLink } from "@/components/MorphLink";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { morph, useMorphNavigate } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/useApiError";
import type { JobFeed } from "@/useJobFeed";

/**
 * One width for everything this screen can be told to do.
 *
 * Left to themselves the buttons are as wide as their words, so "Add" and
 * "Start (3)" sit under each other at two different sizes and read as two
 * different kinds of thing. They are the same kind of thing: the actions of
 * this page. The number is the widest label any of them reaches in either
 * language, so nothing has to wrap to keep them equal.
 */
const ACTION = "min-w-40";

/** What is happening now. Everything finished lives one page over: two lists
 *  with the same rows would leave neither of them meaning anything. */
export function JobsPage({ feed }: { feed: JobFeed }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const input = useRef<HTMLInputElement>(null);
  const navigate = useMorphNavigate();

  const [picked, setPicked] = useState<File[]>([]);
  const [merge, setMerge] = useState(true);
  const [uploading, setUploading] = useState<string | null>(null);
  /** Only the many-jobs route can be partly done, so only it counts. */
  const [sent, setSent] = useState<{ done: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasProvider, setHasProvider] = useState(true);
  const [hasDiarizer, setHasDiarizer] = useState(false);
  const [diarize, setDiarize] = useState(false);

  useEffect(() => {
    void api
      .listProviders()
      .then((providers) => setHasProvider(providers.some((p) => p.kind === "stt")));
    void api.setupStatus().then((status) => setHasDiarizer(status.has_diarizer));
  }, []);

  /** Straight to the recording that was just made: the page that answers for it
   *  now shows the work as well as the words, so there is nowhere better. */
  const openJob = (job: Job) => navigate(`/jobs/${job.id}`);

  /**
   * What was chosen, sent.
   *
   * Nothing goes up before this runs: choosing a file and transcribing it are
   * two decisions, and a drop that started the work immediately meant the
   * second one was made by the first -- with no way back once the wrong file
   * landed on the wrong screen.
   */
  const start = async () => {
    if (picked.length === 0) return;
    setError(null);

    // One recording -- one file on its own, or the whole pile joined into one.
    // Same request either way, and the same page to land on. A lone file takes
    // this path whichever way the switch is left, because "each file becomes a
    // recording of its own" and "join these into one" say the same thing about
    // one file, and only this path opens what it made.
    if (merge || picked.length === 1) {
      setUploading(
        picked.length === 1 ? picked[0].name : t("jobs.mergedName", { total: picked.length }),
      );
      try {
        openJob(await api.uploadJob(picked, diarize));
        setPicked([]);
      } catch (cause) {
        setError(describe(cause));
      } finally {
        setUploading(null);
      }
      return;
    }

    // Sequential rather than parallel: the browser would open them all at once
    // and a queue of large files would compete with itself for the uplink.
    // They travel as separate uploads but under one name, so the archive can
    // show the pile they were dropped in as rather than five loose rows.
    const group = picked.length > 1 ? crypto.randomUUID() : undefined;
    setSent({ done: 0, total: picked.length });
    try {
      for (const [index, file] of picked.entries()) {
        await api.uploadJob(file, diarize, group);
        setSent({ done: index + 1, total: picked.length });
      }
      setPicked([]);
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setSent(null);
      await feed.refresh();
    }
  };

  const addUrl = async (event: FormEvent) => {
    event.preventDefault();
    setAdding(true);
    setError(null);
    try {
      const job = await api.addUrlJob(url.trim(), diarize);
      setUrl("");
      openJob(job);
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setAdding(false);
    }
  };

  const cancel = async (job: Job) => {
    try {
      await api.cancelJob(job.id);
      await feed.refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  /** Dropping chooses; it does not commit. However many arrive, and however
   *  many times: the pile is what is on the screen, not what came in one go. */
  const accept = (files: FileList | null) => {
    const chosen = Array.from(files ?? []);
    if (chosen.length === 0) return;
    void morph(() => setPicked((held) => [...held, ...chosen]));
  };

  // Wrapped in a transition: each row is named after the file it holds, so the
  // browser moves the rows past each other instead of redrawing the list in a
  // new order. With position being the only thing chosen here, seeing it change
  // is the whole feedback.
  const move = (from: number, to: number) =>
    void morph(() =>
      setPicked((held) => {
        if (to < 0 || to >= held.length) return held;
        const next = [...held];
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved);
        return next;
      }),
    );

  const busy = uploading !== null || sent !== null;
  const showArchive = feed.jobs !== null && feed.archive.length > 0;

  return (
    // Centred in what is left of the window rather than stacked under the bar.
    // Up against the bar, on the page's own padding and nothing else. This was
    // centred in the free space for a while, which is what a loose scatter of
    // controls needs to look placed -- but it is one block now, and a block
    // holds its own shape wherever it is put. Centring only moved it away from
    // the bar it belongs to and left a band of nothing between them.
    <div className="grid gap-6">
      {/* The title says what this screen is for; the archive is the other place
          recordings live, so it sits opposite rather than below. Counted rather
          than a preview list: proof the archive exists without pretending to be
          a second copy of it. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("jobs.title")}</h1>
        {showArchive && (
          <Button asChild variant="outline" size="sm" className="group">
            <MorphLink to="/history">
              {t("jobs.inHistory", { total: feed.archive.length })}
              <ArrowRight className="size-3.5 transition-transform duration-(--motion-medium) ease-spring group-hover:translate-x-1" />
            </MorphLink>
          </Button>
        )}
      </div>

      {!hasProvider && (
        <Alert variant="warning">
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {t("jobs.noProvider")}
            {/* Straight to the screen that fixes it, rather than to "look around
                in settings": the address exists, so it may as well be used. */}
            <Button asChild variant="outline" size="sm">
              <MorphLink to="/settings/providers">{t("jobs.openProviders")}</MorphLink>
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* One block, because it is one question: what should be transcribed.
          A file, a link, how to treat the pile, and the button that sends it
          were four things loose on a page with nothing holding them together,
          and the eye had to be told each time that they were parts of the same
          sentence. Inside one surface the order reads by itself, and the
          archive is left outside it -- that is a way off this screen, not a
          part of the thing being composed. */}
      <div data-panel className="panel grid gap-4 rounded-xl p-4">
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            accept(event.dataTransfer.files);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          className={cn(
            // The dashed edge is the whole affordance here, so this one takes the
            // glass fill without the glass border that would erase it.
            "group grid place-items-center gap-3 rounded-lg border-2 border-dashed border-border px-6 py-12 text-center outline-none",
            "transition-[background-color,border-color,box-shadow] duration-(--motion-medium) ease-emphasized",
            "hover:border-primary/60 hover:bg-accent/40 hover:shadow-elevation-3 focus-visible:ring-[3px] focus-visible:ring-ring/50",
            // A file over the window is the one moment this thing should look
            // eager: it lights up and lifts before anything is dropped. It does
            // not swell -- the eagerness is in the colour and the arrow, and a
            // panel of text that grows by a percent only looks mis-set.
            dragging && "border-primary bg-accent/60 shadow-elevation-4",
          )}
        >
          <UploadCloud
            className={cn(
              "size-9 text-muted-foreground transition-transform duration-(--motion-long) ease-spring group-hover:-translate-y-1",
              dragging && "-translate-y-1.5 scale-110 text-primary",
            )}
          />
          <span className="text-sm text-muted-foreground">
            {uploading
              ? t("jobs.uploading", { name: uploading })
              : sent
                ? t("jobs.uploadingCount", sent)
                : t("jobs.dropMany")}
          </span>
          {busy && (
            <Progress className="w-56" indeterminate={sent === null} value={progressOf(sent)} />
          )}
          <input
            ref={input}
            type="file"
            hidden
            multiple
            accept="audio/*,video/*"
            onChange={(event) => {
              accept(event.target.files);
              event.target.value = "";
            }}
          />
        </button>

        {/* Shown in both modes now that neither commits on its own: this is what
          is about to be sent, and it is the only place it can be taken back. */}
        {picked.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-border">
            {picked.map((file, index) => (
              <div
                key={identOf(file)}
                // Named after the file rather than the slot, so a reorder moves
                // this row rather than rewriting the row that sits here -- and
                // only while the list is what is changing, or the row would be
                // cut out of every other transition on this page as well.
                data-morph="quiet"
                style={{ viewTransitionName: identOf(file) }}
                className={cn(
                  "flex animate-rise items-center gap-3 px-4 py-2",
                  index > 0 && "border-t border-border",
                )}
              >
                {/* The number is the point of this list: with everything going into
                  one recording, position is the only thing that is being chosen.
                  One file has no position, so it is not numbered. */}
                {picked.length > 1 && (
                  <span className="w-5 shrink-0 text-sm tabular-nums text-muted-foreground">
                    {index + 1}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-sm">{file.name}</span>
                <span className="shrink-0 text-sm text-muted-foreground">
                  {formatBytes(file.size)}
                </span>
                {merge && picked.length > 1 && (
                  <>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("jobs.moveUp")}
                      disabled={index === 0}
                      onClick={() => move(index, index - 1)}
                    >
                      <ChevronUp className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("jobs.moveDown")}
                      disabled={index === picked.length - 1}
                      onClick={() => move(index, index + 1)}
                    >
                      <ChevronDown className="size-4" />
                    </Button>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("jobs.remove")}
                  onClick={() =>
                    void morph(() => setPicked((held) => held.filter((_, at) => at !== index)))
                  }
                >
                  <X className="size-4" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <form onSubmit={addUrl} className="flex gap-2">
          <Input
            type="url"
            inputMode="url"
            value={url}
            aria-label={t("jobs.urlLabel")}
            placeholder={t("jobs.urlPlaceholder")}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Button type="submit" className={ACTION} disabled={adding || url.trim() === ""}>
            {t("jobs.addUrl")}
          </Button>
        </form>

        {/* The foot of the block: how the pile should be treated, and then the
          button that sends it. Both switches are answers about the same thing
          -- what is staged above -- so they belong beside the action that
          consumes them rather than up beside the page title, where the first
          of them used to sit and be answered before there was anything to
          answer it about. Each explanation is on its own control: a row has
          room for a switch, not for a sentence about one.

          The start button is always here, disabled until there is a pile to
          start: it is the end of this screen, and an end that appears only
          once you have done everything right is one you cannot aim for. */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-border pt-4">
          <Tooltip>
            {/* The pair is the trigger, not the switch: a tooltip trigger writes
              its own `data-state` onto whatever it wraps, and the switch keeps
              checked/unchecked in that same attribute -- wrapped directly, it
              renders as permanently off. */}
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2.5">
                {/* Greyed until there are two files to join, and greyed rather
                  than gone: a control that disappears takes the fact that the
                  choice exists with it. */}
                <Switch
                  id="merge"
                  checked={merge}
                  disabled={picked.length < 2}
                  onCheckedChange={setMerge}
                />
                <Label htmlFor="merge" className="text-sm font-normal">
                  {t("jobs.merge")}
                </Label>
              </div>
            </TooltipTrigger>
            {/* Disabled controls have to say why, or they read as broken. */}
            <TooltipContent>
              {t(
                picked.length < 2
                  ? "jobs.mergeOff"
                  : merge
                    ? "jobs.mergeHint"
                    : "jobs.separateHint",
              )}
            </TooltipContent>
          </Tooltip>

          {/* Applies to whichever of the two routes above is used next: the choice
            belongs to the recording, and both end in the same pipeline. */}
          {hasDiarizer && (
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-2.5">
                  <Switch id="diarize" checked={diarize} onCheckedChange={setDiarize} />
                  <Label htmlFor="diarize" className="text-sm font-normal">
                    {t("jobs.diarize")}
                  </Label>
                </div>
              </TooltipTrigger>
              <TooltipContent>{t("jobs.diarizeHint")}</TooltipContent>
            </Tooltip>
          )}

          <Button
            className={cn(ACTION, "ml-auto")}
            disabled={busy || picked.length === 0}
            onClick={() => void start()}
          >
            {t("jobs.start", { total: picked.length })}
          </Button>
        </div>
      </div>

      {feed.queue.length > 0 && <JobList jobs={feed.queue} onCancel={(job) => void cancel(job)} />}

      {feed.jobs !== null && !showArchive && feed.queue.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("jobs.empty")}</p>
      )}
    </div>
  );
}

function progressOf(sent: { done: number; total: number } | null): number | undefined {
  return sent === null ? undefined : (sent.done / sent.total) * 100;
}

/** A name for the row a file occupies, stable for as long as the file is held
 *  and legal as a CSS identifier. Two byte-identical files picked twice would
 *  collide, and moving one of those past the other is invisible anyway. */
function identOf(file: File): string {
  return `file-${file.lastModified}-${file.size}-${file.name.replace(/[^\p{L}\p{N}]+/gu, "-")}`;
}
