import { AudioLines, Loader2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { api, type ExportFormat, type ExportOptions, type SharedTranscript } from "@/api/client";
import { ExportMenu } from "@/components/ExportMenu";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/useApiError";

/**
 * The one page reachable without an account. It shares no state and no layout
 * with the application: a person following a link is a reader, not a user, and
 * there is nothing here to navigate to.
 */
export function SharedPage() {
  const { token = "" } = useParams();
  const { t, i18n } = useTranslation();
  const describe = useApiErrorMessage();
  const player = useRef<HTMLAudioElement>(null);

  const [transcript, setTranscript] = useState<SharedTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);

  useEffect(() => {
    api
      .readSharedTranscript(token)
      .then(setTranscript)
      .catch((cause: unknown) => setError(describe(cause)));
    // describe is rebuilt on every language change; refetching then is waste.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const current = transcript?.segments.find(
    (segment) => playhead >= segment.start && playhead < segment.end,
  );

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-4xl items-center gap-2 px-4">
          <span className="mr-auto flex items-center gap-2.5 font-semibold tracking-tight">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-xs">
              <AudioLines className="size-4.5" />
            </span>
            {t("app.name")}
          </span>
          <LanguageSwitch />
          <ThemeSwitch />
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-4xl gap-6 px-4 py-8">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {!error && !transcript && (
          <div className="grid place-items-center py-16">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {transcript && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{transcript.title}</h1>
                <p className="text-sm text-muted-foreground">
                  {[
                    transcript.author,
                    transcript.published_on
                      ? new Date(transcript.published_on).toLocaleDateString(i18n.language)
                      : null,
                    transcript.language,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>

              <ExportMenu
                urlFor={(format: ExportFormat, options: ExportOptions) =>
                  api.sharedExportUrl(token, format, options)
                }
                readText={async (format: ExportFormat, options: ExportOptions) => {
                  const response = await fetch(api.sharedExportUrl(token, format, options));
                  return response.text();
                }}
              />
            </div>

            {transcript.has_audio && (
              <audio
                ref={player}
                controls
                preload="metadata"
                src={api.sharedAudioUrl(token)}
                onTimeUpdate={(event) => setPlayhead(event.currentTarget.currentTime)}
                className="w-full"
              />
            )}

            <Card className="gap-0 p-4">
              {transcript.segments.map((segment, index) => {
                const label = segment.speaker;
                const speaks =
                  label && label !== transcript.segments[index - 1]?.speaker
                    ? (transcript.speakers.find((one) => one.label === label)?.display_name ??
                      label)
                    : null;
                return (
                  <Fragment key={segment.idx}>
                    {speaks && (
                      <p className="mt-4 px-2 text-sm font-semibold text-primary first:mt-0">
                        {speaks}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (player.current) {
                          player.current.currentTime = segment.start;
                          void player.current.play();
                        }
                      }}
                      className={cn(
                        "flex w-full gap-4 rounded-md px-2 py-1.5 text-left transition-colors outline-none",
                        "hover:bg-accent/60 focus-visible:ring-[3px] focus-visible:ring-ring/50",
                        segment.idx === current?.idx && "bg-accent",
                      )}
                    >
                      <span className="min-w-14 pt-0.5 font-mono text-sm tabular-nums text-muted-foreground">
                        {formatTimestamp(segment.start)}
                      </span>
                      <span>{segment.text}</span>
                    </button>
                  </Fragment>
                );
              })}
            </Card>
          </>
        )}
      </main>
    </div>
  );
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}
