import { Trash2, VolumeX, X } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, type Job, type JobStatus } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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

interface JobListProps {
  jobs: Job[];
  onCancel?: (job: Job) => void;
  /** Selection is offered only where bulk actions are: the archive. */
  selected?: ReadonlySet<string>;
  onSelect?: (id: string, picked: boolean) => void;
  onDelete?: (job: Job) => void;
  onDropAudio?: (job: Job) => void;
}

/** The same row on both screens: the queue and the archive differ in which jobs
 *  they hold, not in how a job looks. */
export function JobList({
  jobs,
  onCancel,
  selected,
  onSelect,
  onDelete,
  onDropAudio,
}: JobListProps) {
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
          {onSelect && (
            <Checkbox
              checked={selected?.has(job.id) ?? false}
              aria-label={job.title}
              onClick={(event: MouseEvent) => event.stopPropagation()}
              onCheckedChange={(picked) => onSelect(job.id, picked === true)}
            />
          )}

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
            <RowButton
              label={t("jobs.cancel")}
              onClick={() => onCancel(job)}
              icon={<X className="size-4" />}
            />
          )}

          {onDropAudio && job.audio_bytes !== null && (
            <RowButton
              label={t("history.dropAudio")}
              onClick={() => onDropAudio(job)}
              icon={<VolumeX className="size-4" />}
            />
          )}

          {onDelete && (
            <RowButton
              label={t("history.delete")}
              onClick={() => onDelete(job)}
              icon={<Trash2 className="size-4" />}
            />
          )}
        </div>
      ))}
    </Card>
  );
}

function RowButton({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          onClick={(event: MouseEvent) => {
            event.stopPropagation();
            onClick();
          }}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
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

  if (job.audio_bytes !== null) parts.push(formatBytes(job.audio_bytes));

  return parts.join(" · ");
}

export function formatBytes(bytes: number): string {
  const kb = bytes / 1024;
  if (kb < 1) return `${bytes} B`;
  if (kb < 1024) return `${Math.round(kb)} KB`;

  const mb = kb / 1024;
  // One decimal below ten, none above: "1.4 MB" is worth reading, "137.2 MB"
  // is not.
  if (mb < 1024) return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
