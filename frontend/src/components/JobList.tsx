import { X } from "lucide-react";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, type Job, type JobStatus } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useCodeMessage } from "@/useApiError";
import { isPending } from "@/useJobFeed";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success";

const STATUS_VARIANT: Record<JobStatus, BadgeVariant> = {
  queued: "outline",
  running: "default",
  cancelling: "outline",
  cancelled: "secondary",
  done: "success",
  failed: "destructive",
};

/** The same row on both screens: the queue and the archive differ in which jobs
 *  they hold, not in how a job looks. Cancelling is offered only where it can
 *  still do something. */
export function JobList({ jobs, onCancel }: { jobs: Job[]; onCancel?: (job: Job) => void }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const describeCode = useCodeMessage();

  return (
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

          {onCancel && isPending(job) && job.status !== "cancelling" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("jobs.cancel")}
                  onClick={(event: MouseEvent) => {
                    event.stopPropagation();
                    onCancel(job);
                  }}
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
