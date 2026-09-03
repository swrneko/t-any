import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Job } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type Period = "any" | "today" | "week" | "month";
type Length = "any" | "short" | "medium" | "long";
type Kind = "any" | "audio" | "video";

export interface Filters {
  period: Period;
  length: Length;
  kind: Kind;
}

export const NO_FILTERS: Filters = { period: "any", length: "any", kind: "any" };

/** Days a period covers, counted back from now. `today` is the calendar day,
 *  which is the one people mean literally. */
const DAYS: Record<Exclude<Period, "any" | "today">, number> = { week: 7, month: 30 };

/** Where the minutes are cut. Five is roughly a voice note, thirty is roughly a
 *  meeting; the point is to separate those two, not to be exact. */
const MINUTES: Record<Exclude<Length, "any">, [number, number]> = {
  short: [0, 5],
  medium: [5, 30],
  long: [30, Number.POSITIVE_INFINITY],
};

const VIDEO = new Set([
  "mp4", "m4v", "mkv", "mov", "webm", "avi", "wmv", "flv", "ts", "mpg", "mpeg", "3gp",
]);
const AUDIO = new Set([
  "mp3", "m4a", "wav", "flac", "ogg", "oga", "opus", "aac", "wma", "aif", "aiff", "alac",
]);

/**
 * Audio or video, as far as the name says.
 *
 * The backend keeps no such column: everything it stores about a recording is
 * of the audio it extracted, and by then what arrived is forgotten. What is
 * left is the filename, and for a link there may not even be one -- a page
 * handed to yt-dlp is neither, and only "any" shows it. Guessing harder than
 * this would mean guessing wrong on the rows it matters for.
 */
function kindOf(job: Job): Exclude<Kind, "any"> | null {
  const first = job.source_ref.split(",")[0].trim().split(/[?#]/)[0];
  const dot = first.lastIndexOf(".");
  if (dot < 0) return null;
  const extension = first.slice(dot + 1).toLowerCase();
  if (VIDEO.has(extension)) return "video";
  if (AUDIO.has(extension)) return "audio";
  return null;
}

/** Whether a recording survives the filters. A recording whose length is not
 *  known cannot be said to be under five minutes or over thirty, so it is only
 *  shown while nothing is being asked of the length. */
export function matches(job: Job, filters: Filters, now: number): boolean {
  if (filters.period !== "any") {
    const made = new Date(job.created_at).getTime();
    if (filters.period === "today") {
      const midnight = new Date(now);
      midnight.setHours(0, 0, 0, 0);
      if (made < midnight.getTime()) return false;
    } else if (made < now - DAYS[filters.period] * 86_400_000) {
      return false;
    }
  }

  if (filters.length !== "any") {
    if (job.duration_sec === null) return false;
    const [from, to] = MINUTES[filters.length];
    const minutes = job.duration_sec / 60;
    if (minutes < from || minutes >= to) return false;
  }

  if (filters.kind !== "any" && kindOf(job) !== filters.kind) return false;

  return true;
}

/**
 * The one bar the archive is asked through: the words to look for, and which
 * recordings are worth showing at all.
 *
 * Search and the filters are one control because they answer the same question
 * from two sides, and because a field on its own above a list is where a page
 * puts a thing it has not decided about. Everything here is applied in the
 * browser -- the archive is fetched whole either way (see the pager) -- so a
 * filter costs a pass over an array and never a round trip.
 */
export function ArchiveBar({
  query,
  onQuery,
  filters,
  onFilters,
}: {
  query: string;
  onQuery: (query: string) => void;
  filters: Filters;
  onFilters: (filters: Filters) => void;
}) {
  const { t } = useTranslation();
  const asked =
    query !== "" ||
    filters.period !== "any" ||
    filters.length !== "any" ||
    filters.kind !== "any";

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-full border border-border bg-card py-1.5 pr-1.5 pl-4">
      <Search className="size-4 shrink-0 text-muted-foreground" />

      {/* A bare input, not the field component: inside a surface of its own the
          field's fill, border and focus ring would be a second control drawn
          inside the first. The bar is the field; this is where the letters go. */}
      <input
        autoFocus
        value={query}
        aria-label={t("search.label")}
        placeholder={t("search.placeholder")}
        className="min-w-40 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        onChange={(event) => onQuery(event.target.value)}
      />

      <div className="flex flex-wrap items-center gap-1.5">
        <Chip
          value={filters.period}
          onChange={(period) => onFilters({ ...filters, period: period as Period })}
          options={["any", "today", "week", "month"]}
          name="period"
        />
        <Chip
          value={filters.length}
          onChange={(length) => onFilters({ ...filters, length: length as Length })}
          options={["any", "short", "medium", "long"]}
          name="length"
        />
        <Chip
          value={filters.kind}
          onChange={(kind) => onFilters({ ...filters, kind: kind as Kind })}
          options={["any", "audio", "video"]}
          name="kind"
        />

        {/* One press puts the archive back, which is the way out of a filter
            somebody set three chips ago and cannot see the effect of. */}
        {asked && (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("history.filters.reset")}
            onClick={() => {
              onQuery("");
              onFilters(NO_FILTERS);
            }}
          >
            <X className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * One filter, as a chip.
 *
 * The resting option is named after the filter rather than after itself -- the
 * chip reads "Date" until it reads "Today" -- so a filter that is doing nothing
 * still says what it would do, and one that is doing something says only that.
 * A set chip is drawn in the accent colour rather than filled with it: inside
 * the page every field resolves to the card's own fill, and a rule that says so
 * outranks any utility a component could write here.
 */
function Chip({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        size="sm"
        aria-label={t(`history.filters.${name}.label`)}
        className={cn(
          "rounded-full border-transparent",
          value !== "any" && "border-primary text-primary",
        )}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {t(`history.filters.${name}.${option}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
