import { ArrowLeft, Copy, Loader2, Pencil } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import {
  api,
  type Job,
  type Speaker,
  type Transcript,
  type TranscriptSegment,
} from "@/api/client";
import { ExportMenu } from "@/components/ExportMenu";
import { ShareDialog } from "@/components/ShareDialog";
import { SummaryPanel } from "@/components/SummaryPanel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/useApiError";

export function TranscriptPage() {
  const { jobId = "" } = useParams();
  const [params] = useSearchParams();
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const player = useRef<HTMLAudioElement>(null);

  const [job, setJob] = useState<Job | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTimestamps, setShowTimestamps] = useState(true);
  const [copied, setCopied] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    Promise.all([api.readJob(jobId), api.readTranscript(jobId)])
      .then(([loadedJob, loadedTranscript]) => {
        setJob(loadedJob);
        setTranscript(loadedTranscript);
      })
      .catch((cause: unknown) => setError(describe(cause)));
    // describe is rebuilt on every language change; refetching then is waste.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // A search result links to the moment it found, not just to the recording.
  const at = Number(params.get("at") ?? Number.NaN);
  useEffect(() => {
    if (!transcript || Number.isNaN(at) || !player.current) return;
    player.current.currentTime = at;
    setPlayhead(at);
  }, [transcript, at]);

  const copy = async () => {
    if (!transcript) return;
    await navigator.clipboard.writeText(transcript.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (error) {
    return (
      <div className="grid gap-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!job || !transcript) {
    return (
      <div className="grid place-items-center py-16">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const current = transcript.segments.find(
    (segment) => playhead >= segment.start && playhead < segment.end,
  );

  const nameOf = (label: string) =>
    transcript.speakers.find((speaker) => speaker.label === label)?.display_name ?? label;

  const correct = async (segment: TranscriptSegment) => {
    setEditing(null);
    if (draft.trim() === segment.text.trim()) return;
    const saved = await api.correctSegment(job.id, segment.idx, draft);
    const segments = transcript.segments.map((one) => (one.idx === saved.idx ? saved : one));
    // `text` is derived, so it has to be re-derived: it is what the copy
    // button copies, and it would otherwise still hold the old wording.
    setTranscript({
      ...transcript,
      segments,
      text: segments
        .map((one) => one.text)
        .join(" ")
        .trim(),
    });
  };

  return (
    <div className="grid gap-6">
      <BackLink />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>
          {transcript.language && (
            <p className="text-sm text-muted-foreground">
              {t("transcript.language", { language: transcript.language })}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Label htmlFor="timestamps" className="text-sm text-muted-foreground">
            {t("transcript.timestamps")}
          </Label>
          <Switch id="timestamps" checked={showTimestamps} onCheckedChange={setShowTimestamps} />
          <Button variant="outline" size="sm" onClick={() => void copy()}>
            <Copy className="size-4" />
            {copied ? t("transcript.copied") : t("transcript.copy")}
          </Button>
          <ExportMenu
            urlFor={(format, options) => api.exportUrl(job.id, format, options)}
            readText={(format, options) => api.readExport(job.id, format, options)}
          />
          <ShareDialog jobId={job.id} />
        </div>
      </div>

      {/* A player with nothing to play reads as a broken page, so the recording
          having been freed is said in words instead. */}
      {job.audio_bytes === null ? (
        <p className="text-sm text-muted-foreground">{t("transcript.audioGone")}</p>
      ) : (
        <audio
          ref={player}
          controls
          preload="metadata"
          src={api.audioUrl(job.id)}
          onTimeUpdate={(event) => setPlayhead(event.currentTarget.currentTime)}
          className="w-full"
        />
      )}

      {transcript.speakers.length > 0 && (
        <SpeakerBar
          speakers={transcript.speakers}
          onRename={(id, name) =>
            void api.renameSpeaker(job.id, id, name).then((saved) =>
              setTranscript({
                ...transcript,
                speakers: transcript.speakers.map((one) => (one.id === saved.id ? saved : one)),
              }),
            )
          }
        />
      )}

      <Card className="gap-0 p-4">
        {transcript.segments.map((segment, index) => {
          const active = segment.idx === current?.idx;
          // Named once per turn, not once per segment: a name repeated on every
          // line is what makes a diarised transcript unreadable.
          const speaks =
            segment.speaker && segment.speaker !== transcript.segments[index - 1]?.speaker
              ? nameOf(segment.speaker)
              : null;
          return (
            <Fragment key={segment.idx}>
              {speaks && (
                <p className="mt-4 px-2 text-sm font-semibold text-primary first:mt-0">{speaks}</p>
              )}
              {editing === segment.idx ? (
                <Textarea
                  autoFocus
                  rows={2}
                  value={draft}
                  className="my-1"
                  aria-label={t("transcript.correct")}
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={() => void correct(segment)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.blur();
                    }
                    // Escape puts the text back, and the equality check below
                    // turns the blur that follows into nothing.
                    if (event.key === "Escape") {
                      setDraft(segment.text);
                      setEditing(null);
                    }
                  }}
                />
              ) : (
                <div className="group flex items-start">
                  <button
                    type="button"
                    onClick={() => {
                      if (player.current) {
                        player.current.currentTime = segment.start;
                        void player.current.play();
                      }
                    }}
                    className={cn(
                      "flex flex-1 gap-4 rounded-md px-2 py-1.5 text-left transition-colors outline-none",
                      "hover:bg-accent/60 focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      active && "bg-accent",
                    )}
                  >
                    {showTimestamps && (
                      <span className="min-w-14 pt-0.5 font-mono text-sm tabular-nums text-muted-foreground">
                        {formatTimestamp(segment.start)}
                      </span>
                    )}
                    <span className={cn(active && "font-medium", segment.edited && "italic")}>
                      {segment.text}
                    </span>
                  </button>
                  {/* Kept out of the seek button: clicking a line is how you
                      jump to it, and one click cannot mean two things. */}
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("transcript.correct")}
                    title={t(segment.edited ? "transcript.corrected" : "transcript.correct")}
                    className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                    onClick={() => {
                      setDraft(segment.text);
                      setEditing(segment.idx);
                    }}
                  >
                    <Pencil className="size-3.5 text-muted-foreground" />
                  </Button>
                </div>
              )}
            </Fragment>
          );
        })}
      </Card>

      <SummaryPanel jobId={job.id} />
    </div>
  );
}

function SpeakerBar({
  speakers,
  onRename,
}: {
  speakers: Speaker[];
  onRename: (id: string, displayName: string) => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-muted-foreground">{t("transcript.speakers")}</span>
      {speakers.map((speaker) =>
        editing === speaker.id ? (
          <Input
            key={speaker.id}
            autoFocus
            value={draft}
            className="h-8 w-40"
            placeholder={speaker.label}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => {
              setEditing(null);
              if (draft.trim() !== (speaker.display_name ?? "")) onRename(speaker.id, draft);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
              // Escape leaves the name as it was: a rename typed into the wrong
              // speaker has to be abandonable.
              if (event.key === "Escape") {
                setDraft(speaker.display_name ?? "");
                setEditing(null);
              }
            }}
          />
        ) : (
          <Button
            key={speaker.id}
            variant="outline"
            size="sm"
            title={t("transcript.rename")}
            onClick={() => {
              setDraft(speaker.display_name ?? "");
              setEditing(speaker.id);
            }}
          >
            <Pencil className="size-3 text-muted-foreground" />
            {speaker.display_name ?? speaker.label}
          </Button>
        ),
      )}
    </div>
  );
}

function BackLink() {
  const { t } = useTranslation();
  return (
    <Button asChild variant="ghost" size="sm" className="justify-self-start">
      {/* Back to where transcripts live, which is the archive rather than the
          upload screen this one may have been opened from. */}
      <Link to="/history">
        <ArrowLeft className="size-4" />
        {t("transcript.back")}
      </Link>
    </Button>
  );
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}
