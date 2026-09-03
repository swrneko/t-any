import { useCallback, useEffect, useState } from "react";

import { api, TERMINAL_STATUSES, type Job } from "@/api/client";

export const isPending = (job: Job) => !TERMINAL_STATUSES.includes(job.status);

export interface JobFeed {
  /** Null until the first answer arrives; an empty array means an empty instance. */
  jobs: Job[] | null;
  /** What is happening now, plus whatever finished under this session's eye. */
  queue: Job[];
  /** Everything terminal. The same rows the archive page lists. */
  archive: Job[];
  refresh: () => Promise<void>;
}

/**
 * One feed for both screens, held above the router.
 *
 * It lives here rather than in the page because a job that finishes while you
 * are reading its transcript would otherwise disappear from the queue before
 * you got back: the set of ids seen working survives navigation, and only a
 * reload clears it. A reload is the one gesture that means "start over".
 */
export function useJobFeed(): JobFeed {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [watched, setWatched] = useState<ReadonlySet<string>>(new Set());

  const remember = useCallback((next: Job[]) => {
    setJobs(next);
    setWatched((seen) => {
      const fresh = next.filter((job) => isPending(job) && !seen.has(job.id));
      return fresh.length === 0 ? seen : new Set([...seen, ...fresh.map((job) => job.id)]);
    });
  }, []);

  const refresh = useCallback(async () => {
    const next = await api.listJobs().catch(() => null);
    if (next) remember(next);
  }, [remember]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Reopened whenever work starts: the server ends the stream once everything
  // is terminal, so an idle page holds no connection at all.
  const pendingCount = jobs?.filter(isPending).length ?? 0;
  useEffect(() => {
    if (pendingCount === 0) return;
    return api.watchJobs(remember);
  }, [pendingCount, remember]);

  const all = jobs ?? [];
  return {
    jobs,
    queue: all.filter((job) => isPending(job) || watched.has(job.id)),
    archive: all.filter((job) => !isPending(job)),
    refresh,
  };
}
