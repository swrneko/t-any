import { ArrowRight, ChevronDown, ChevronUp, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, type Job } from "@/api/client";
import { formatBytes, JobList } from "@/components/JobList";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/useApiError";
import type { JobFeed } from "@/useJobFeed";

/** What is happening now. Everything finished lives one page over: two lists
 *  with the same rows would leave neither of them meaning anything. */
export function JobsPage({ feed }: { feed: JobFeed }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const [batch, setBatch] = useState(false);
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

  const uploadOne = async (file: File) => {
    setUploading(file.name);
    setError(null);
    try {
      openJob(await api.uploadJob(file, diarize));
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setUploading(null);
    }
  };

  /** The whole pile at once: one recording out of all of it, or one job each. */
  const startBatch = async () => {
    if (picked.length === 0) return;
    setError(null);

    if (merge) {
      setUploading(t("jobs.mergedName", { total: picked.length }));
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
    setSent({ done: 0, total: picked.length });
    try {
      for (const [index, file] of picked.entries()) {
        await api.uploadJob(file, diarize);
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

  const accept = (files: FileList | null) => {
    const chosen = Array.from(files ?? []);
    if (chosen.length === 0) return;
    if (batch) setPicked((held) => [...held, ...chosen]);
    else void uploadOne(chosen[0]);
  };

  const move = (from: number, to: number) =>
    setPicked((held) => {
      if (to < 0 || to >= held.length) return held;
      const next = [...held];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });

  const busy = uploading !== null || sent !== null;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("jobs.title")}</h1>

        {/* Two buttons rather than a control we do not otherwise own: the choice
            is binary and it changes what the drop zone below means. */}
        <div className="flex rounded-lg border border-border p-0.5">
          {[false, true].map((wanted) => (
            <Button
              key={String(wanted)}
              size="sm"
              variant={batch === wanted ? "secondary" : "ghost"}
              onClick={() => {
                setBatch(wanted);
                setPicked([]);
              }}
            >
              {t(wanted ? "jobs.mode.batch" : "jobs.mode.single")}
            </Button>
          ))}
        </div>
      </div>

      {!hasProvider && (
        <Alert variant="warning">
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {t("jobs.noProvider")}
            {/* Straight to the screen that fixes it, rather than to "look around
                in settings": the address exists, so it may as well be used. */}
            <Button asChild variant="outline" size="sm">
              <Link to="/settings/providers">{t("jobs.openProviders")}</Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

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
          "grid place-items-center gap-3 rounded-xl border-2 border-dashed border-border bg-card/40 px-6 py-12 text-center transition-colors outline-none",
          "hover:border-primary/60 hover:bg-accent/40 focus-visible:ring-[3px] focus-visible:ring-ring/50",
          dragging && "border-primary bg-accent/60",
        )}
      >
        <UploadCloud className="size-9 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">
          {uploading
            ? t("jobs.uploading", { name: uploading })
            : sent
              ? t("jobs.uploadingCount", sent)
              : t(batch ? "jobs.dropMany" : "jobs.drop")}
        </span>
        {busy && <Progress className="w-56" indeterminate={sent === null} value={progressOf(sent)} />}
        <input
          ref={input}
          type="file"
          hidden
          multiple={batch}
          accept="audio/*,video/*"
          onChange={(event) => {
            accept(event.target.files);
            event.target.value = "";
          }}
        />
      </button>

      {batch && picked.length > 0 && (
        <Card className="gap-0 overflow-hidden p-0">
          {picked.map((file, index) => (
            <div
              key={`${file.name}-${index}`}
              className={cn(
                "flex items-center gap-3 px-4 py-2",
                index > 0 && "border-t border-border",
              )}
            >
              {/* The number is the point of this list: with everything going into
                  one recording, position is the only thing that is being chosen. */}
              <span className="w-5 shrink-0 text-sm tabular-nums text-muted-foreground">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm">{file.name}</span>
              <span className="shrink-0 text-sm text-muted-foreground">
                {formatBytes(file.size)}
              </span>
              {merge && (
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
                onClick={() => setPicked((held) => held.filter((_, at) => at !== index))}
              >
                <X className="size-4" />
              </Button>
            </div>
          ))}
        </Card>
      )}

      {batch && (
        <div className="grid gap-3">
          <div className="flex items-center gap-3">
            <Switch id="merge" checked={merge} onCheckedChange={setMerge} />
            <Label htmlFor="merge" className="text-sm font-normal">
              {t("jobs.merge")}
            </Label>
            <span className="text-sm text-muted-foreground">
              {t(merge ? "jobs.mergeHint" : "jobs.separateHint")}
            </span>
          </div>
          <Button
            className="justify-self-start"
            disabled={busy || picked.length === 0}
            onClick={() => void startBatch()}
          >
            {t("jobs.start", { total: picked.length })}
          </Button>
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
        <Button type="submit" disabled={adding || url.trim() === ""}>
          {t("jobs.addUrl")}
        </Button>
      </form>

      {/* Applies to whichever of the two above is used next: the choice belongs
          to the recording, and both routes end in the same pipeline. */}
      {hasDiarizer && (
        <div className="flex items-center gap-3">
          <Switch id="diarize" checked={diarize} onCheckedChange={setDiarize} />
          <Label htmlFor="diarize" className="text-sm font-normal">
            {t("jobs.diarize")}
          </Label>
          <span className="text-sm text-muted-foreground">{t("jobs.diarizeHint")}</span>
        </div>
      )}

      {feed.queue.length > 0 && <JobList jobs={feed.queue} onCancel={(job) => void cancel(job)} />}

      {feed.jobs !== null &&
        (feed.archive.length > 0 ? (
          // A counted line, not a preview list: proof the archive exists without
          // pretending to be a second copy of it.
          <Link
            to="/history"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            {t("jobs.inHistory", { total: feed.archive.length })}
            <ArrowRight className="size-3.5" />
          </Link>
        ) : (
          feed.queue.length === 0 && <p className="text-sm text-muted-foreground">{t("jobs.empty")}</p>
        ))}
    </div>
  );
}

function progressOf(sent: { done: number; total: number } | null): number | undefined {
  return sent === null ? undefined : (sent.done / sent.total) * 100;
}
