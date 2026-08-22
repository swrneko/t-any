import { Copy, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, TERMINAL_STATUSES, type Preset, type Summary } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApiErrorMessage, useCodeMessage } from "@/useApiError";
import { usePresetLabel } from "@/usePresetLabel";

export function SummaryPanel({ jobId }: { jobId: string }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const describeCode = useCodeMessage();
  const label = usePresetLabel();

  const [presets, setPresets] = useState<Preset[]>([]);
  const [chosen, setChosen] = useState("");
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setSummaries(await api.listSummaries(jobId));
  }, [jobId]);

  useEffect(() => {
    void api.listPresets().then((loaded) => {
      setPresets(loaded);
      setChosen((current) => current || (loaded[0]?.id ?? ""));
    });
    void refresh();
  }, [refresh]);

  // One stream per unfinished summary. Unlike the job list this stays at one or
  // two at a time: a summary is asked for by hand, one click at a time.
  const pending = summaries.filter((summary) => !TERMINAL_STATUSES.includes(summary.status));
  const pendingIds = pending.map((summary) => summary.id).join(",");
  useEffect(() => {
    if (!pendingIds) return;
    const closers = pendingIds.split(",").map((id) =>
      api.watchSummary(id, (updated) =>
        setSummaries((current) =>
          current.map((summary) => (summary.id === updated.id ? updated : summary)),
        ),
      ),
    );
    return () => closers.forEach((close) => close());
  }, [pendingIds]);

  const summarise = async () => {
    setError(null);
    try {
      await api.createSummary(jobId, chosen);
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const remove = async (summary: Summary) => {
    await api.deleteSummary(summary.id);
    await refresh();
  };

  const copy = async (summary: Summary) => {
    await navigator.clipboard.writeText(summary.content);
    setCopied(summary.id);
    setTimeout(() => setCopied(null), 2000);
  };

  const selected = presets.find((preset) => preset.id === chosen);

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold tracking-tight">{t("summary.title")}</h2>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-64 gap-2">
          <Label htmlFor="summary-preset">{t("summary.preset")}</Label>
          <Select value={chosen} onValueChange={setChosen}>
            <SelectTrigger id="summary-preset" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {presets.map((preset) => (
                <SelectItem key={preset.id} value={preset.id}>
                  {label(preset).name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button onClick={() => void summarise()} disabled={!chosen}>
          <Sparkles className="size-4" />
          {t("summary.run")}
        </Button>
      </div>

      {selected && (
        <p className="-mt-2 text-xs text-muted-foreground">{label(selected).description}</p>
      )}

      {summaries.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("summary.empty")}</p>
      )}

      {summaries.map((summary) => (
        <Card key={summary.id} className="gap-3 p-5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{summary.preset_name}</span>
              {summary.model_used && (
                <Badge variant="outline" className="font-mono">
                  {summary.model_used}
                </Badge>
              )}
              {!TERMINAL_STATUSES.includes(summary.status) && (
                <Badge>{t(`jobs.status.${summary.status}`)}</Badge>
              )}
              {copied === summary.id && (
                <span className="text-xs text-muted-foreground">{t("transcript.copied")}</span>
              )}
            </div>

            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("transcript.copy")}
                onClick={() => void copy(summary)}
              >
                <Copy className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("presets.delete")}
                onClick={() => void remove(summary)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </div>

          {summary.status === "failed" ? (
            <Alert variant="destructive">
              <AlertDescription>
                {describeCode(summary.error_code, summary.error_params)}
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {!TERMINAL_STATUSES.includes(summary.status) && (
                <Progress
                  value={summary.progress * 100}
                  indeterminate={summary.progress === 0}
                />
              )}
              <div className="text-sm leading-relaxed whitespace-pre-wrap">{summary.content}</div>
            </>
          )}
        </Card>
      ))}
    </div>
  );
}
