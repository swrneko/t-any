import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** How many rows a page holds. The archive is the only list long enough to
 *  need the question asked, and these are the four answers worth offering. */
export const PAGE_SIZES = [10, 30, 50, 100] as const;

const STORAGE_KEY = "history.pageSize";

/** The size to start at, which is the smallest: a first visit should show a
 *  short list, and anybody who wants a longer one says so once and is
 *  remembered. A stored value is only believed if it is still one of the four
 *  on offer, so changing that list cannot leave somebody on a size the
 *  selector has no name for. */
function storedSize(): number {
  const value = Number(localStorage.getItem(STORAGE_KEY));
  return PAGE_SIZES.includes(value as (typeof PAGE_SIZES)[number]) ? value : PAGE_SIZES[0];
}

export interface Paging {
  /** The slice to render. */
  page: number;
  size: number;
  from: number;
  to: number;
  pages: number;
  setPage: (page: number) => void;
  setSize: (size: number) => void;
}

/**
 * Where in a list we are, kept honest against a list that changes under us.
 *
 * The archive is fetched whole and lives above the router, so this is a
 * question about reading rather than about fetching: nothing is saved on the
 * wire by turning to page two. What it saves is the browser laying out four
 * hundred rows to show thirty, and the eye finding the one it wants among
 * them.
 *
 * `total` shrinks when a recording is deleted, and the page that was being read
 * can stop existing -- so the page is clamped on every render rather than only
 * when it is set, and lands on the last page that still has rows on it.
 */
export function usePaging(total: number): Paging {
  const [size, setStoredSize] = useState(storedSize);
  const [page, setPage] = useState(1);

  const pages = Math.max(1, Math.ceil(total / size));
  const current = Math.min(page, pages);

  useEffect(() => {
    if (page !== current) setPage(current);
  }, [page, current]);

  const setSize = (next: number) => {
    localStorage.setItem(STORAGE_KEY, String(next));
    setStoredSize(next);
    // The row that was at the top of page three is nowhere near the top of
    // page three at a different size, so there is no position to preserve.
    setPage(1);
  };

  return {
    page: current,
    size,
    from: total === 0 ? 0 : (current - 1) * size + 1,
    to: Math.min(current * size, total),
    pages,
    setPage,
    setSize,
  };
}

/**
 * The footer under a paged list: what is on screen, how much of it fits, and
 * the way to the rest.
 *
 * It is drawn even when everything fits on one page. A footer that appears once
 * a list crosses thirty rows is a control you have to discover twice -- and the
 * size selector is the reason you might want it to appear at all.
 */
export function Pager({ paging, total }: { paging: Paging; total: number }) {
  const { t } = useTranslation();
  const { page, size, from, to, pages, setPage, setSize } = paging;

  return (
    // The same pill the player is: a footer that is a row of loose controls on
    // the background reads as things left over under the list, and this one
    // belongs to the list above it.
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-full border border-border bg-card py-1.5 pr-1.5 pl-5">
      <p className="text-sm text-muted-foreground">{t("history.range", { from, to, total })}</p>

      <div className="flex items-center gap-3">
        <Select value={String(size)} onValueChange={(value) => setSize(Number(value))}>
          <SelectTrigger size="sm" aria-label={t("history.perPage")} className="w-20">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((option) => (
              <SelectItem key={option} value={String(option)}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={page === 1}
            aria-label={t("history.previous")}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>

          {window_(page, pages).map((step, index) =>
            step === null ? (
              <span key={`gap-${index}`} className="px-1 text-sm text-muted-foreground">
                &hellip;
              </span>
            ) : (
              <Button
                key={step}
                variant="ghost"
                size="icon-sm"
                aria-current={step === page ? "page" : undefined}
                className={cn("relative", step === page && "text-accent-foreground")}
                onClick={() => setPage(step)}
              >
                {step === page && (
                  <span aria-hidden className="absolute inset-0 -z-10 rounded-full bg-accent" />
                )}
                {step}
              </Button>
            ),
          )}

          <Button
            variant="ghost"
            size="icon-sm"
            disabled={page === pages}
            aria-label={t("history.next")}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * The numbers to draw: the ends, the neighbourhood of where we are, and a gap
 * wherever a run was left out.
 *
 * A row of buttons that grows with the archive is a row that eventually does not
 * fit, and the first thing it pushes off the line is the one you were about to
 * press. Seven slots is what a phone holds without wrapping.
 */
function window_(page: number, pages: number): (number | null)[] {
  const steps = new Set([1, pages, page - 1, page, page + 1]);
  if (page <= 3) [2, 3, 4].forEach((step) => steps.add(step));
  if (page >= pages - 2) [pages - 3, pages - 2, pages - 1].forEach((step) => steps.add(step));

  const shown = [...steps].filter((step) => step >= 1 && step <= pages).sort((a, b) => a - b);
  return shown.flatMap((step, index) =>
    index > 0 && step - shown[index - 1] > 1 ? [null, step] : [step],
  );
}
