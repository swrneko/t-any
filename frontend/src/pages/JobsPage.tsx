import { ArrowRight, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, type Job } from "@/api/client";
import { JobList } from "@/components/JobList";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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

  const [uploading, setUploading] = useState<string | null>(null);
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

  const upload = async (file: File) => {
    setUploading(file.name);
    setError(null);
    try {
      await api.uploadJob(file, diarize);
      await feed.refresh();
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setUploading(null);
    }
  };

  const addUrl = async (event: FormEvent) => {
    event.preventDefault();
    setAdding(true);
    setError(null);
    try {
      await api.addUrlJob(url.trim(), diarize);
      setUrl("");
      await feed.refresh();
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

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void upload(file);
  };

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("jobs.title")}</h1>

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
        onDrop={onDrop}
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
          {uploading ? t("jobs.uploading", { name: uploading }) : t("jobs.drop")}
        </span>
        {uploading && <Progress className="w-56" indeterminate />}
        <input
          ref={input}
          type="file"
          hidden
          accept="audio/*,video/*"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
      </button>

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
