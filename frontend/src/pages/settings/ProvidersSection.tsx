import { Check, KeyRound, Loader2, Pencil, Plug, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  api,
  type Provider,
  type ProviderDraft,
  type ProviderKind,
  type ProviderProbe,
} from "@/api/client";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useApiErrorMessage, useCodeMessage } from "@/useApiError";

const BLANK: ProviderDraft = {
  kind: "stt",
  name: "",
  base_url: "",
  default_model: null,
  context_tokens: null,
  is_default: false,
};

const toDraft = (provider: Provider): ProviderDraft => ({
  kind: provider.kind,
  name: provider.name,
  base_url: provider.base_url,
  default_model: provider.default_model,
  context_tokens: provider.context_tokens,
  is_default: provider.is_default,
});

interface Editing {
  id: string | null;
  draft: ProviderDraft;
  /** What the saved key should become: kept, cleared, or replaced by typing. */
  key: { typed: string; cleared: boolean; mask: string | null };
}

export function ProvidersSection({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const describeCode = useCodeMessage();

  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [probe, setProbe] = useState<ProviderProbe | null>(null);
  const [probing, setProbing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setProviders(await api.listProviders().catch(() => []));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const open = (provider: Provider | null) => {
    setProbe(null);
    setError(null);
    setEditing(
      provider
        ? {
            id: provider.id,
            draft: toDraft(provider),
            key: { typed: "", cleared: false, mask: provider.api_key },
          }
        : { id: null, draft: BLANK, key: { typed: "", cleared: false, mask: null } },
    );
  };

  const patch = (changes: Partial<ProviderDraft>) =>
    setEditing((current) =>
      current ? { ...current, draft: { ...current.draft, ...changes } } : current,
    );

  const save = async () => {
    if (!editing) return;
    setError(null);
    // Absent leaves the key alone; only a deliberate clear or a typed value
    // travels, so saving a form nobody touched cannot wipe a working key.
    const key = editing.key.cleared ? "" : editing.key.typed || undefined;
    try {
      if (editing.id) {
        await api.updateProvider(editing.id, { ...editing.draft, api_key: key });
      } else {
        await api.createProvider({ ...editing.draft, api_key: key });
      }
      setEditing(null);
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const remove = async (provider: Provider) => {
    setError(null);
    try {
      await api.deleteProvider(provider.id);
      await refresh();
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const test = async () => {
    if (!editing) return;
    setProbing(true);
    setProbe(null);
    try {
      // A saved provider is probed by id, so its key never has to be retyped
      // just to find out whether the address answers.
      const untouched = editing.id !== null && !editing.key.typed && !editing.key.cleared;
      setProbe(
        await api.testProvider(
          untouched
            ? { provider_id: editing.id! }
            : { base_url: editing.draft.base_url, api_key: editing.key.typed || undefined },
        ),
      );
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setProbing(false);
    }
  };

  return (
    <div className="grid gap-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            {t("settings.sections.providers")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("settings.providers.explanation")}</p>
        </div>
        {isAdmin && (
          <Button onClick={() => open(null)}>
            <Plus className="size-4" />
            {t("settings.providers.new")}
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {providers !== null &&
        (providers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("settings.providers.empty")}</p>
        ) : (
          <Card className="gap-0 overflow-hidden p-0">
            {providers.map((provider, index) => (
              <div
                key={provider.id}
                className={`flex items-start gap-3 px-4 py-3 ${index > 0 ? "border-t border-border" : ""}`}
              >
                <div className="grid min-w-0 flex-1 gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{provider.name}</span>
                    <Badge variant="outline">
                      {t(`settings.providers.kind.${provider.kind}`)}
                    </Badge>
                    {provider.is_default && (
                      <Badge variant="secondary">{t("settings.providers.default")}</Badge>
                    )}
                  </div>
                  <p className="truncate font-mono text-sm text-muted-foreground">
                    {provider.base_url}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {[
                      provider.default_model ?? t("settings.providers.noModel"),
                      provider.context_tokens
                        ? t("settings.providers.context", { tokens: provider.context_tokens })
                        : null,
                      provider.api_key ?? t("settings.providers.noKey"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>

                {isAdmin && (
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("settings.providers.edit")}
                      onClick={() => open(provider)}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={t("settings.providers.delete")}
                      onClick={() => void remove(provider)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </Card>
        ))}

      {/* Deleting every provider and restarting brings them back from the
          environment. That is the recovery path, but it looks like a ghost
          unless it is written down. */}
      <p className="text-sm text-muted-foreground">{t("settings.providers.seeding")}</p>

      <Dialog open={editing !== null} onOpenChange={(isOpen) => !isOpen && setEditing(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing?.id ? t("settings.providers.edit") : t("settings.providers.new")}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4">
            <Field label={t("settings.providers.kind.label")}>
              {(id) => (
                <Select
                  value={editing?.draft.kind ?? "stt"}
                  // Fixed once saved: a provider's kind decides which protocol
                  // it is spoken to with, so changing it is a different row.
                  disabled={editing?.id !== null}
                  onValueChange={(value) => patch({ kind: value as ProviderKind })}
                >
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stt">{t("settings.providers.kind.stt")}</SelectItem>
                    <SelectItem value="llm">{t("settings.providers.kind.llm")}</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </Field>

            <Field label={t("settings.providers.name")}>
              {(id) => (
                <Input
                  id={id}
                  value={editing?.draft.name ?? ""}
                  onChange={(event) => patch({ name: event.target.value })}
                  required
                />
              )}
            </Field>

            <Field label={t("settings.providers.baseUrl")} hint={t("settings.providers.urlHint")}>
              {(id) => (
                <Input
                  id={id}
                  value={editing?.draft.base_url ?? ""}
                  placeholder="http://host.docker.internal:8000/v1"
                  className="font-mono text-sm"
                  onChange={(event) => patch({ base_url: event.target.value })}
                  required
                />
              )}
            </Field>

            <Field label={t("settings.providers.apiKey")}>
              {(id) => (
                <div className="flex gap-2">
                  <Input
                    id={id}
                    type="password"
                    autoComplete="off"
                    value={editing?.key.typed ?? ""}
                    placeholder={
                      editing?.key.cleared
                        ? t("settings.providers.keyCleared")
                        : (editing?.key.mask ?? t("settings.providers.noKey"))
                    }
                    onChange={(event) =>
                      setEditing((current) =>
                        current
                          ? {
                              ...current,
                              key: { ...current.key, typed: event.target.value, cleared: false },
                            }
                          : current,
                      )
                    }
                  />
                  {editing?.key.mask && (
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label={t("settings.providers.clearKey")}
                      title={t("settings.providers.clearKey")}
                      onClick={() =>
                        setEditing((current) =>
                          current
                            ? { ...current, key: { ...current.key, typed: "", cleared: true } }
                            : current,
                        )
                      }
                    >
                      <KeyRound className="size-4" />
                    </Button>
                  )}
                </div>
              )}
            </Field>

            <Field label={t("settings.providers.model")}>
              {(id) =>
                probe?.models.length ? (
                  // Once the endpoint has listed what it has, picking beats
                  // typing: a model name with a typo fails at the first job.
                  <Select
                    value={editing?.draft.default_model ?? ""}
                    onValueChange={(value) => patch({ default_model: value })}
                  >
                    <SelectTrigger id={id} className="w-full">
                      <SelectValue placeholder={t("settings.providers.noModel")} />
                    </SelectTrigger>
                    <SelectContent>
                      {probe.models.map((model) => (
                        <SelectItem key={model} value={model}>
                          {model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id={id}
                    value={editing?.draft.default_model ?? ""}
                    onChange={(event) => patch({ default_model: event.target.value || null })}
                  />
                )
              }
            </Field>

            {editing?.draft.kind === "llm" && (
              <Field
                label={t("settings.providers.contextTokens")}
                hint={t("settings.providers.contextHint")}
              >
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={1024}
                    step={1024}
                    value={editing?.draft.context_tokens ?? ""}
                    onChange={(event) =>
                      patch({ context_tokens: Number(event.target.value) || null })
                    }
                  />
                )}
              </Field>
            )}

            <div className="flex items-center gap-3">
              <Switch
                id="provider-default"
                checked={editing?.draft.is_default ?? false}
                onCheckedChange={(checked) => patch({ is_default: checked })}
              />
              <label htmlFor="provider-default" className="text-sm">
                {t("settings.providers.makeDefault")}
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="outline"
                disabled={probing || !editing?.draft.base_url}
                onClick={() => void test()}
              >
                {probing ? <Loader2 className="size-4 animate-spin" /> : <Plug className="size-4" />}
                {t("settings.providers.test")}
              </Button>

              {probe && (
                <span className="flex items-center gap-1.5 text-sm">
                  {probe.reachable ? (
                    <>
                      <Check className="size-4 text-success" />
                      {t("settings.providers.answered", {
                        ms: probe.latency_ms ?? 0,
                        models: probe.models.length,
                      })}
                    </>
                  ) : (
                    <>
                      <X className="size-4 text-destructive" />
                      {describeCode(probe.error_code, { status: probe.status })}
                    </>
                  )}
                </span>
              )}
            </div>

            <p className="text-sm text-muted-foreground">{t("settings.providers.testHint")}</p>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              {t("presets.cancel")}
            </Button>
            <Button
              onClick={() => void save()}
              disabled={!editing?.draft.name || !editing?.draft.base_url}
            >
              {t("presets.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
