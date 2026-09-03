import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TranscriptSearchProps {
  query: string;
  onQuery: (query: string) => void;
  /** How many lines hold it, and which of them is being looked at. */
  found: number;
  at: number;
  onStep: (delta: number) => void;
  className?: string;
}

/**
 * Finding a word inside one recording.
 *
 * Not the archive's search: that one asks the database which recordings mention
 * something, and answers with rows. This one is the page's own find bar over a
 * transcript that is already in the browser -- so it costs nothing, answers as
 * you type, and counts corrections, which the index behind the other one only
 * learns about by trigger.
 */
export function TranscriptSearch({
  query,
  onQuery,
  found,
  at,
  onStep,
  className,
}: TranscriptSearchProps) {
  const { t } = useTranslation();
  const asked = query.trim().length > 0;

  return (
    // A bare input rather than the Input component: this is a field inside a
    // pill, so the pill carries the edge and the fill, and a second bordered
    // box within it would be a border drawn twice.
    <div
      className={cn(
        "flex h-9 items-center gap-1.5 rounded-full border border-border bg-card pr-1 pl-3",
        className,
      )}
    >
      <Search className="size-4 shrink-0 text-muted-foreground" />
      <input
        type="search"
        value={query}
        placeholder={t("transcript.find")}
        aria-label={t("transcript.find")}
        className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          onStep(event.shiftKey ? -1 : 1);
        }}
      />

      {asked && (
        <>
          {/* Lines, not occurrences: a word said twice in one breath is one
              place to go, and "2 of 47" has to mean the same thing as the
              two arrows beside it. */}
          <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
            {found === 0 ? t("transcript.noHits") : `${at + 1}/${found}`}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={found === 0}
            aria-label={t("transcript.previousHit")}
            onClick={() => onStep(-1)}
          >
            <ChevronUp className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={found === 0}
            aria-label={t("transcript.nextHit")}
            onClick={() => onStep(1)}
          >
            <ChevronDown className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("transcript.clearFind")}
            onClick={() => onQuery("")}
          >
            <X className="size-4" />
          </Button>
        </>
      )}
    </div>
  );
}
