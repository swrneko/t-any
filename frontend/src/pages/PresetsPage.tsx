import { Copy, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type Preset, type PresetDraft } from "@/api/client";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/useApiError";
import { usePresetLabel } from "@/usePresetLabel";

const BLANK: PresetDraft = {
  name: "",
  description: "",
  system_prompt: "",
  user_template: "{transcript}",
  model_override: null,
  provider_id: null,
  temperature: 0.3,
  output_format: "markdown",
};

const toDraft = (preset: Preset): PresetDraft => ({
  name: preset.name,
  description: preset.description,
  system_prompt: preset.system_prompt,
  user_template: preset.user_template,
  model_override: preset.model_override,
  provider_id: preset.provider_id,
  temperature: preset.temperature,
  output_format: preset.output_format,
});

export function PresetsPage() {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const label = usePresetLabel();

  const [presets, setPresets] = useState<Preset[]>([]);
  const [editing, setEditing] = useState<{ id: string | null; draft: PresetDraft } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setPresets(await api.listPresets());
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const patch = (changes: Partial<PresetDraft>) =>
    setEditing((current) =>
      current ? { ...current, draft: { ...current.draft, ...changes } } : current,
    );

  const save = async () => {
    if (!editing) return;
    setError(null);
    try {
      if (editing.id) {
        await api.updatePreset(editing.id, editing.draft);
      } else {
        await api.createPreset(editing.draft);
      }
      setEditing(null);
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const remove = async (preset: Preset) => {
    try {
      await api.deletePreset(preset.id);
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t("presets.title")}</h1>
        <Button onClick={() => setEditing({ id: null, draft: BLANK })}>
          <Plus className="size-4" />
          {t("presets.new")}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="gap-0 overflow-hidden p-0">
        {presets.map((preset, index) => {
          const { name, description } = label(preset);
          return (
            <div
              key={preset.id}
              className={cn(
                "flex items-center gap-3 px-4 py-3",
                index > 0 && "border-t border-border",
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{name}</span>
                  {preset.is_builtin && (
                    <Badge variant="outline">{t("presets.builtinTag")}</Badge>
                  )}
                </div>
                <p className="truncate text-sm text-muted-foreground">{description}</p>
              </div>

              {preset.is_builtin ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("presets.duplicate")}
                      onClick={() =>
                        setEditing({
                          id: null,
                          draft: { ...toDraft(preset), name: t("presets.copyOf", { name }) },
                        })
                      }
                    >
                      <Copy className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t("presets.duplicate")}</TooltipContent>
                </Tooltip>
              ) : (
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("presets.edit")}
                    onClick={() => setEditing({ id: preset.id, draft: toDraft(preset) })}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("presets.delete")}
                    onClick={() => void remove(preset)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </Card>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing?.id ? t("presets.edit") : t("presets.new")}</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4">
            <Field label={t("presets.name")}>
              {(id) => (
                <Input
                  id={id}
                  value={editing?.draft.name ?? ""}
                  onChange={(event) => patch({ name: event.target.value })}
                  required
                />
              )}
            </Field>

            <Field label={t("presets.description")}>
              {(id) => (
                <Input
                  id={id}
                  value={editing?.draft.description ?? ""}
                  onChange={(event) => patch({ description: event.target.value })}
                />
              )}
            </Field>

            <Field label={t("presets.systemPrompt")}>
              {(id) => (
                <Textarea
                  id={id}
                  rows={3}
                  value={editing?.draft.system_prompt ?? ""}
                  onChange={(event) => patch({ system_prompt: event.target.value })}
                  required
                />
              )}
            </Field>

            <Field label={t("presets.userTemplate")} hint={t("presets.templateHint")}>
              {(id) => (
                <Textarea
                  id={id}
                  rows={4}
                  className="font-mono text-sm"
                  value={editing?.draft.user_template ?? ""}
                  onChange={(event) => patch({ user_template: event.target.value })}
                  required
                />
              )}
            </Field>

            <Field label={t("presets.temperature")}>
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  step={0.1}
                  min={0}
                  max={2}
                  value={editing?.draft.temperature ?? 0.3}
                  onChange={(event) => patch({ temperature: Number(event.target.value) })}
                />
              )}
            </Field>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              {t("presets.cancel")}
            </Button>
            <Button onClick={() => void save()}>{t("presets.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
