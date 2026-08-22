import { Loader2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { api, MARK_END, MARK_START, type SearchHit } from "@/api/client";
import { JobList } from "@/components/JobList";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { JobFeed } from "@/useJobFeed";

/**
 * Everything that finished, and the search over it.
 *
 * Search is not a screen of its own: it is the same archive, filtered by what
 * was said instead of by when it arrived. An empty field means "show me all of
 * it", which is what an archive page is for anyway.
 */
export function HistoryPage({ feed }: { feed: JobFeed }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";

  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">{t("history.title")}</h1>

      <div className="relative">
        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={query}
          className="pl-9"
          aria-label={t("search.label")}
          placeholder={t("search.placeholder")}
          onChange={(event) => setParams(event.target.value ? { q: event.target.value } : {})}
        />
      </div>

      {!searching &&
        (feed.archive.length > 0 ? (
          <JobList jobs={feed.archive} />
        ) : (
          feed.jobs !== null && <p className="text-sm text-muted-foreground">{t("history.empty")}</p>
        ))}

      {searching && busy && hits === null && (
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      )}

      {searching && hits !== null && hits.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("search.nothing", { query })}</p>
      )}

      {searching && hits !== null && hits.length > 0 && (
        <Card className="gap-0 overflow-hidden p-0">
          {hits.map((hit) => (
            <Link
              key={`${hit.job_id}-${hit.idx}`}
              to={`/jobs/${hit.job_id}?at=${Math.floor(hit.start)}`}
              className="grid gap-1 border-t border-border px-4 py-3 first:border-t-0 hover:bg-accent/50"
            >
              <span className="truncate text-sm font-medium">{hit.job_title}</span>
              <span className="text-sm text-muted-foreground">
                <Excerpt text={hit.excerpt} />
              </span>
            </Link>
          ))}
        </Card>
      )}
    </div>
  );
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
