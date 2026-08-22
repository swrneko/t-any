import { UploadCloud, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
  type MouseEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, TERMINAL_STATUSES, type Job, type JobStatus } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useApiErrorMessage, useCodeMessage } from "@/useApiError";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success";

const STATUS_VARIANT: Record<JobStatus, BadgeVariant> = {
  queued: "outline",
  running: "default",
  cancelling: "outline",
  cancelled: "secondary",
  done: "success",
  failed: "destructive",
};

const isPending = (job: Job) => !TERMINAL_STATUSES.includes(job.status);

export function JobsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const describe = useApiErrorMessage();
  const describeCode = useCodeMessage();
  const input = useRef<HTMLInputElement>(null);

  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasProvider, setHasProvider] = useState(true);
  const [hasDiarizer, setHasDiarizer] = useState(false);
  const [diarize, setDiarize] = useState(false);

  const refresh = useCallback(async () => {
    setJobs(await api.listJobs());
  }, []);

  useEffect(() => {
    void refresh();
    void api
      .listProviders()
      .then((providers) => setHasProvider(providers.some((p) => p.kind === "stt")));
    void api.setupStatus().then((status) => setHasDiarizer(status.has_diarizer));
  }, [refresh]);

  // Reopened whenever work starts: the server ends the stream once everything
  // is terminal, so an idle page holds no connection at all.
  const pendingCount = jobs?.filter(isPending).length ?? 0;
  useEffect(() => {
    if (pendingCount === 0) return;
    return api.watchJobs(setJobs);
  }, [pendingCount]);

  const upload = async (file: File) => {
    setUploading(file.name);
    setError(null);
    try {
      await api.uploadJob(file, diarize);
      await refresh();
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
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setAdding(false);
    }
  };

  const cancel = async (event: MouseEvent, job: Job) => {
    event.stopPropagation();
    try {
      await api.cancelJob(job.id);
      await refresh();
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
          <AlertDescription>{t("jobs.noProvider")}</AlertDescription>
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

      {jobs && jobs.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("jobs.empty")}</p>
      )}

      {jobs && jobs.length > 0 && (
        <Card className="gap-0 overflow-hidden p-0">
          {jobs.map((job, index) => (
            <div
              key={job.id}
              className={cn(
                "flex items-center gap-3 px-4 py-3",
                index > 0 && "border-t border-border",
                job.status === "done" && "cursor-pointer hover:bg-accent/50",
              )}
              onClick={() => {
                if (job.status === "done") navigate(`/jobs/${job.id}`);
              }}
            >
              {job.has_thumbnail && (
                <img
                  src={api.thumbnailUrl(job.id)}
                  alt=""
                  className="h-10 w-16 shrink-0 rounded-md border border-border object-cover"
                />
              )}

              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{job.title}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {job.status === "failed"
                    ? describeCode(job.error_code, job.error_params)
                    : formatMeta(job, i18n.language)}
                </p>
              </div>

              {job.status === "running" && (
                <Progress
                  className="w-20"
                  value={job.progress * 100}
                  indeterminate={job.progress === 0}
                />
              )}

              <Badge variant={STATUS_VARIANT[job.status]}>{t(`jobs.status.${job.status}`)}</Badge>

              {isPending(job) && job.status !== "cancelling" && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("jobs.cancel")}
                      onClick={(event) => void cancel(event, job)}
                    >
                      <X className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t("jobs.cancel")}</TooltipContent>
                </Tooltip>
              )}
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

/** Dates follow the chosen language, not the browser's: someone reading the app
 *  in Russian should not be shown 5/14/2026. */
function formatMeta(job: Job, locale: string): string {
  const parts: string[] = [];
  if (job.author) parts.push(job.author);
  if (job.published_on) parts.push(new Date(job.published_on).toLocaleDateString(locale));

  if (job.duration_sec === null) {
    parts.push(new Date(job.created_at).toLocaleString(locale));
  } else {
    const minutes = Math.floor(job.duration_sec / 60);
    const seconds = Math.round(job.duration_sec % 60);
    parts.push(`${minutes}:${String(seconds).padStart(2, "0")}`);
  }

  return parts.join(" · ");
}
