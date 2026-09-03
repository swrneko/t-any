import { Layers, Trash2, VolumeX, X } from "lucide-react";
import type { MouseEvent, PointerEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, type Job, type JobStatus } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { pressRipple, useMorphNavigate } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useCodeMessage } from "@/useApiError";
import { isPending } from "@/useJobFeed";

type BadgeVariant =
  "default" | "secondary" | "destructive" | "outline" | "success";

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
export function JobList(props: JobListProps) {
  const { t } = useTranslation();
  const { jobs, selected, onSelect } = props;

  let position = 0;

  return (
    <Card className="gap-0 divide-y divide-border overflow-hidden p-0">
      {blocksOf(jobs).map((block) =>
        block.batch === null ? (
          <JobRow key={block.jobs[0].id} job={block.jobs[0]} at={position++} {...props} />
        ) : (
          // Files dropped in together and transcribed apart. Left as loose rows
          // they read as five unrelated recordings that happen to be adjacent,
          // which is exactly what they are not.
          //
          // Said with structure rather than with colour, and that is not a
          // preference. The block used to carry an accent fill and an accent
          // rule down its left edge -- and `accent` is the colour a row takes
          // when the pointer is over it or when it has been ticked, so a batch
          // was painted in the one colour on this screen that already means
          // "chosen". Four recordings that arrived together looked like four
          // recordings somebody had selected. There is no tint available that
          // says grouping here: the list's own hover state has the only one.
          //
          // So the members are indented under a caption and threaded on a
          // hairline, which is how every file tree has said "these are inside
          // that" -- and indentation is the one signal a selection never uses.
          // The caption's checkbox stays in the outer column and the members'
          // move in with them, so ticking the group and ticking one of its
          // members are visibly different gestures.
          //
          // Under all of it, a tonal step, which is Material's answer to
          // "these belong together" and this file's own (see the `panel`
          // utility). `--group` is the token for that and it is the wrong one
          // here: it is set one shade off `--background`, and this block sits
          // inside a card, where it lands two values out of 255 from the fill
          // it is meant to be distinguished from. `--muted` is the step that
          // exists relative to a card -- ten values in dark, the same in light,
          // visible in both, and neutral enough that nothing about it says
          // "chosen".
          <div
            key={block.batch}
            className="animate-rise bg-muted"
            style={{ animationDelay: delayFor(position++) }}
          >
            <div className="flex items-center gap-3 px-4 py-2.5">
              {onSelect && (
                <Checkbox
                  checked={block.jobs.every((job) => selected?.has(job.id))}
                  aria-label={t("jobs.batch", { count: block.jobs.length })}
                  onCheckedChange={(picked) =>
                    block.jobs.forEach((job) => onSelect(job.id, picked === true))
                  }
                />
              )}
              <Layers className="size-3.5 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {t("jobs.batch", { count: block.jobs.length })}
              </span>
            </div>
            {/* The group is one arrival; its members do not each get one of
                their own or the block would ripple down the screen.

                The rule along the top is the caption's, and the block's own
                bottom edge is drawn by the list it sits in -- so the block is
                closed on both sides rather than only underneath. */}
            <div className="ml-6 divide-y divide-border border-t border-l border-border">
              {block.jobs.map((job) => (
                <JobRow key={job.id} job={job} {...props} />
              ))}
            </div>
          </div>
        ),
      )}
    </Card>
  );
}

/** Rows arrive one after another rather than all at once, but the queue stops
 *  waiting after the first handful: a list of forty should not take two seconds
 *  to finish appearing. */
function delayFor(at: number): string {
  return `${Math.min(at, 8) * 45}ms`;
}

interface Block {
  /** Null for a recording that arrived on its own. */
  batch: string | null;
  jobs: Job[];
}

/** Members of a batch collapse onto the position of the first one seen, so the
 *  order of the list is otherwise untouched -- and a batch whose members were
 *  deleted down to one is a row again, not a group of one. */
function blocksOf(jobs: Job[]): Block[] {
  const blocks: Block[] = [];
  const held = new Map<string, Block>();

  for (const job of jobs) {
    const batch = job.batch_id;
    if (batch === null) {
      blocks.push({ batch: null, jobs: [job] });
      continue;
    }
    const block = held.get(batch);
    if (block) {
      block.jobs.push(job);
      continue;
    }
    const fresh: Block = { batch, jobs: [job] };
    held.set(batch, fresh);
    blocks.push(fresh);
  }

  return blocks.map((block) =>
    block.jobs.length > 1 ? block : { batch: null, jobs: block.jobs },
  );
}

function JobRow({
  job,
  at,
  onCancel,
  selected,
  onSelect,
  onDelete,
  onDropAudio,
}: JobListProps & { job: Job; at?: number }) {
  const { t, i18n } = useTranslation();
  const navigate = useMorphNavigate();
  const describeCode = useCodeMessage();

  const address = `/jobs/${job.id}`;

  // The row used to name itself for the length of the trip, so that it became
  // the page rather than being replaced by it. It cannot: the box that travels
  // grows from a row to a page, and an engine that stretches a picture into its
  // box draws the whole page squashed and lets it unfold. The page arrives on
  // its own now, like every other screen.
  const open = () => {
    void navigate(address);
  };

  return (
    <div
      className={cn(
        "ripple flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors duration-(--motion-short) ease-standard hover:bg-accent/50",
        at !== undefined && "animate-rise",
      )}
      style={{ animationDelay: at === undefined ? undefined : delayFor(at) }}
      onPointerDown={(event: PointerEvent<HTMLDivElement>) => pressRipple(event)}
      // Every row, not only the finished ones: the job's own page reports
      // the work while it happens and the words once it is over.
      onClick={open}
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
        <p className="flex items-center gap-2 truncate font-medium">
          <span className="truncate">{job.title}</span>
          {/* A joined recording looks like any other row otherwise, and its
                  title only hints at the rest with a "+2". The names it was made
                  of are on the badge, where somebody looking for one can find
                  it without opening the recording. */}
          {job.parts > 1 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="shrink-0 font-normal">
                  <Layers className="size-3" />
                  {t("jobs.parts", { total: job.parts })}
                </Badge>
              </TooltipTrigger>
              <TooltipContent>{job.source_ref}</TooltipContent>
            </Tooltip>
          )}
        </p>
        <p className="truncate text-sm text-muted-foreground">
          {job.status === "failed"
            ? describeCode(job.error_code, job.error_params)
            : // While something is happening, say what: the badge only says
              // that the job is running, and a download that reports its
              // stage no longer looks like a job that has hung.
              job.stage
              ? t(`jobs.stage.${job.stage}`)
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

      <Badge variant={STATUS_VARIANT[job.status]}>
        {t(`jobs.status.${job.status}`)}
      </Badge>

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
  if (job.published_on)
    parts.push(new Date(job.published_on).toLocaleDateString(locale));

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
