import { Loader2, Trash2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { api, MARK_END, MARK_START, type Job, type SearchHit } from "@/api/client";
import { ArchiveBar, matches, NO_FILTERS, type Filters } from "@/components/ArchiveBar";
import { formatBytes, JobList } from "@/components/JobList";
import { MorphLink } from "@/components/MorphLink";
import { Pager, usePaging } from "@/components/Pager";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApiErrorMessage } from "@/useApiError";
import type { JobFeed } from "@/useJobFeed";

/** What is about to happen, and to how many recordings. */
interface Pending {
  jobs: Job[];
  audioOnly: boolean;
}

/**
 * Everything that finished, and the search over it.
 *
 * Search is not a screen of its own: it is the same archive, filtered by what
 * was said instead of by when it arrived. An empty field means "show me all of
 * it", which is what an archive page is for anyway.
 */
export function HistoryPage({ feed }: { feed: JobFeed }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";

  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim() === "") {
      setHits(null);
      return;
    }
    setBusy(true);
    // Typing is faster than the round trip, so the query waits for a pause.
    const timer = setTimeout(() => {
      api
        .search(query)
        .then(setHits)
        .finally(() => setBusy(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  const searching = query.trim() !== "";

  const select = (id: string, take: boolean) =>
    setPicked((current) => {
      const next = new Set(current);
      if (take) next.add(id);
      else next.delete(id);
      return next;
    });

  const chosen = feed.archive.filter((job) => picked.has(job.id));

  // Filtering happens before paging and before anything is counted, so "1-10 of
  // 16" is ten of the sixteen being shown rather than of the archive. `now` is
  // read once per render: a period counted from a different instant for every
  // row is a list that can disagree with itself.
  const now = Date.now();
  const kept = feed.archive.filter((job) => matches(job, filters, now));

  // Over the whole archive, not over the page: a selection survives turning to
  // the next one, which is the only reason to select across pages at all.
  const paging = usePaging(kept.length);
  const shown = kept.slice(paging.from - 1, paging.to);

  // The filters narrow what was found as well as what was listed: a hit points
  // at a recording, and a recording the filters have put away should not come
  // back because a word in it matched.
  const keptIds = new Set(kept.map((job) => job.id));
  const found = filters === NO_FILTERS ? hits : (hits?.filter((hit) => keptIds.has(hit.job_id)) ?? null);

  const commit = async () => {
    if (!pending) return;
    setError(null);
    const ids = pending.jobs.map((job) => job.id);
    try {
      if (ids.length === 1) {
        if (pending.audioOnly) await api.deleteJobAudio(ids[0]);
        else await api.deleteJob(ids[0]);
      } else {
        await api.deleteJobs(ids, pending.audioOnly);
      }
      setPending(null);
      setPicked(new Set());
      await feed.refresh();
    } catch (cause) {
      setError(describe(cause));
      setPending(null);
    }
  };

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("history.title")}</h1>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <ArchiveBar
        query={query}
        onQuery={(next) => setParams(next ? { q: next } : {})}
        filters={filters}
        onFilters={setFilters}
      />

      {!searching && chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {t("history.chosen", { n: chosen.length })}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPending({ jobs: chosen, audioOnly: true })}
          >
            <VolumeX className="size-4" />
            {t("history.dropAudio")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPending({ jobs: chosen, audioOnly: false })}
          >
            <Trash2 className="size-4" />
            {t("history.delete")}
          </Button>
        </div>
      )}

      {!searching &&
        (kept.length > 0 ? (
          <>
            {/* Keyed on the page, so turning one is an arrival rather than the
                same rows quietly holding different words. The filters are in
                the key too: a narrowed list is a different list. */}
            <JobList
              key={`${paging.page}-${paging.size}-${filters.period}${filters.length}${filters.kind}`}
              jobs={shown}
              selected={picked}
              onSelect={select}
              onDelete={(job) => setPending({ jobs: [job], audioOnly: false })}
              onDropAudio={(job) => setPending({ jobs: [job], audioOnly: true })}
            />
            <Pager paging={paging} total={kept.length} />
          </>
        ) : (
          // An archive with nothing in it and an archive with nothing left
          // after the filters look identical and are not the same problem.
          feed.jobs !== null && (
            <p className="text-sm text-muted-foreground">
              {t(feed.archive.length > 0 ? "history.noMatch" : "history.empty")}
            </p>
          )
        ))}

      {searching && busy && found === null && (
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      )}

      {searching && found !== null && found.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("search.nothing", { query })}</p>
      )}

      {searching && found !== null && found.length > 0 && (
        <Card className="gap-0 overflow-hidden p-0">
          {found.map((hit) => (
            <MorphLink
              key={`${hit.job_id}-${hit.idx}`}
              to={`/jobs/${hit.job_id}?at=${Math.floor(hit.start)}`}
              className="ripple grid animate-rise gap-1 border-t border-border px-4 py-3 transition-colors duration-(--motion-short) first:border-t-0 hover:bg-accent/50"
            >
              <span className="truncate text-sm font-medium">{hit.job_title}</span>
              <span className="text-sm text-muted-foreground">
                <Excerpt text={hit.excerpt} />
              </span>
            </MorphLink>
          ))}
        </Card>
      )}

      {/* Asked, not undone. An "undo" toast would mean a deleted_at column, a
          filter in every query and files swept later; this is rarer than that
          is expensive. */}
      <Dialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {pending?.audioOnly ? t("history.dropAudio") : t("history.delete")}
            </DialogTitle>
            <DialogDescription>
              {/* One recording and a selection read differently in every
                  language, so they are two strings rather than a plural rule. */}
              {t(
                `history.${pending?.audioOnly ? "confirmAudio" : "confirmDelete"}${
                  (pending?.jobs.length ?? 0) === 1 ? "One" : "Many"
                }`,
                { n: pending?.jobs.length ?? 0 },
              )}
              {freed(pending) > 0 && ` ${t("history.frees", { size: formatBytes(freed(pending)) })}`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPending(null)}>
              {t("presets.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void commit()}>
              {pending?.audioOnly ? t("history.dropAudio") : t("history.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function freed(pending: Pending | null): number {
  return (pending?.jobs ?? []).reduce((total, job) => total + (job.audio_bytes ?? 0), 0);
}

/**
 * The server marks the match with two control characters rather than with tags,
 * so highlighting is a split, never an injection: whatever was said out loud
 * stays text.
 */
function Excerpt({ text }: { text: string }) {
  return (
    <>
      {text.split(MARK_START).map((chunk, index) => {
        if (index === 0) return <span key={index}>{chunk}</span>;
        const [match, ...rest] = chunk.split(MARK_END);
        return (
          <span key={index}>
            <mark className="rounded-sm bg-primary/20 px-0.5 text-foreground">{match}</mark>
            {rest.join(MARK_END)}
          </span>
        );
      })}
    </>
  );
}
