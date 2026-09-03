import { Check, Copy, KeyRound, Loader2, Plus, Send, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  api,
  type ApiTokenSummary,
  type CreatedApiToken,
  type Webhook,
  type WebhookTest,
} from "@/api/client";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiErrorMessage, useCodeMessage } from "@/useApiError";

export function ApiSection({ isAdmin }: { isAdmin: boolean }) {
  const { t, i18n } = useTranslation();
  const describe = useApiErrorMessage();

  const [tokens, setTokens] = useState<ApiTokenSummary[]>([]);
  const [name, setName] = useState("");
  const [minted, setMinted] = useState<CreatedApiToken | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTokens()
      .then(setTokens)
      .catch(() => undefined);
  }, []);

  const create = async () => {
    setError(null);
    try {
      const created = await api.createToken(name.trim());
      setMinted(created);
      setName("");
      setTokens(await api.listTokens());
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const revoke = async (id: string) => {
    setError(null);
    try {
      await api.revokeToken(id);
      if (minted?.id === id) setMinted(null);
      setTokens(await api.listTokens());
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const copy = async () => {
    if (!minted) return;
    await navigator.clipboard.writeText(minted.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{t("settings.sections.api")}</h2>
        <p className="text-sm text-muted-foreground">{t("settings.tokens.explanation")}</p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {minted && (
        <Alert variant="warning">
          <AlertDescription className="grid gap-2">
            <span>{t("settings.tokens.shownOnce")}</span>
            <span className="flex gap-2">
              <Input readOnly value={minted.token} className="font-mono text-xs" />
              <Button
                variant="outline"
                size="icon"
                aria-label={t("settings.tokens.copy")}
                onClick={() => void copy()}
              >
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      )}

      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void create();
        }}
      >
        <div className="grid flex-1 gap-2">
          <Label htmlFor="token-name">{t("settings.tokens.name")}</Label>
          <Input
            id="token-name"
            value={name}
            placeholder={t("settings.tokens.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={name.trim() === ""}>
          <Plus className="size-4" />
          {t("settings.tokens.create")}
        </Button>
      </form>

      {tokens.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("settings.tokens.empty")}</p>
      ) : (
        <Card className="gap-0 overflow-hidden p-0">
          {tokens.map((token, index) => (
            <div
              key={token.id}
              className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? "border-t border-border" : ""}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{token.name}</p>
                <p className="text-sm text-muted-foreground">
                  {token.last_used_at
                    ? t("settings.tokens.lastUsed", {
                        date: new Date(token.last_used_at).toLocaleString(i18n.language),
                      })
                    : t("settings.tokens.neverUsed")}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("settings.tokens.revoke")}
                onClick={() => void revoke(token.id)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
        </Card>
      )}

      {isAdmin && <WebhookCard />}

      <Documentation />
    </div>
  );
}

/** Where a finished job is announced. Stored here rather than in the
 *  environment, because the receiver changes more often than anyone wants to
 *  restart a container. */
function WebhookCard() {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();
  const describeCode = useCodeMessage();

  const [hook, setHook] = useState<Webhook | null>(null);
  const [typed, setTyped] = useState<string>("");
  const [cleared, setCleared] = useState(false);
  const [called, setCalled] = useState<WebhookTest | null>(null);
  const [calling, setCalling] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .readWebhook()
      .then(setHook)
      .catch(() => undefined);
  }, []);

  const save = async () => {
    if (!hook) return;
    setError(null);
    try {
      const secret = cleared ? "" : typed || undefined;
      setHook(await api.writeWebhook(hook.url?.trim() || null, secret));
      setTyped("");
      setCleared(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const call = async () => {
    setCalling(true);
    setCalled(null);
    setError(null);
    try {
      setCalled(await api.testWebhook());
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setCalling(false);
    }
  };

  if (!hook) return null;

  return (
    <Card className="grid gap-4 p-4">
      <div>
        <h3 className="font-medium">{t("settings.api.webhook")}</h3>
        <p className="text-sm text-muted-foreground">{t("settings.api.webhookHint")}</p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Field label={t("settings.api.webhookUrl")}>
        {(id) => (
          <Input
            id={id}
            value={hook.url ?? ""}
            placeholder="http://automation.lan/hooks/tany"
            className="font-mono text-sm"
            onChange={(event) => setHook({ ...hook, url: event.target.value })}
          />
        )}
      </Field>

      <Field label={t("settings.api.webhookSecret")} hint={t("settings.api.secretHint")}>
        {(id) => (
          <div className="flex gap-2">
            <Input
              id={id}
              type="password"
              autoComplete="off"
              value={typed}
              placeholder={
                cleared ? t("settings.providers.keyCleared") : (hook.secret ?? t("settings.api.noSecret"))
              }
              onChange={(event) => {
                setTyped(event.target.value);
                setCleared(false);
              }}
            />
            {hook.secret && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label={t("settings.api.clearSecret")}
                title={t("settings.api.clearSecret")}
                onClick={() => {
                  setTyped("");
                  setCleared(true);
                }}
              >
                <KeyRound className="size-4" />
              </Button>
            )}
          </div>
        )}
      </Field>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => void save()}>{t("presets.save")}</Button>
        <Button variant="outline" disabled={calling || !hook.url} onClick={() => void call()}>
          {calling ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          {t("settings.api.sendTest")}
        </Button>
        {saved && <span className="text-sm text-success">{t("settings.storage.saved")}</span>}
        {called && (
          <span className="flex items-center gap-1.5 text-sm">
            {called.delivered ? (
              <>
                <Check className="size-4 text-success" />
                {t("settings.api.delivered", { status: called.status ?? 200 })}
              </>
            ) : (
              <>
                <X className="size-4 text-destructive" />
                {describeCode(called.error_code, { status: called.status })}
              </>
            )}
          </span>
        )}
      </div>
    </Card>
  );
}

/**
 * The four things about this API that its own schema does not say.
 *
 * No hand-written endpoint reference: /docs is generated and always current,
 * while a second copy would be wrong within one milestone.
 */
function Documentation() {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const base = window.location.origin;
  const example = [
    `# 1. queue a recording`,
    `curl -X POST ${base}/api/jobs \\`,
    `  -H "Authorization: Bearer tany_..." \\`,
    `  -F file=@meeting.m4a`,
    ``,
    `# 2. watch it, or just wait`,
    `curl ${base}/api/jobs/JOB_ID -H "Authorization: Bearer tany_..."`,
    ``,
    `# 3. take the words`,
    `curl "${base}/api/jobs/JOB_ID/export?format=txt&timestamps=true" \\`,
    `  -H "Authorization: Bearer tany_..."`,
  ].join("\n");

  const copy = async () => {
    await navigator.clipboard.writeText(example);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="grid gap-4 p-4">
      <div>
        <h3 className="font-medium">{t("settings.api.docs")}</h3>
        <p className="text-sm text-muted-foreground">
          {t("settings.api.baseUrl")} <code className="font-mono">{base}/api</code>
        </p>
      </div>

      <div className="relative">
        <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">{example}</pre>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t("transcript.copy")}
          className="absolute top-2 right-2"
          onClick={() => void copy()}
        >
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">{t("settings.api.errors")}</p>

      <Button asChild variant="outline" size="sm" className="justify-self-start">
        <a href="/docs" target="_blank" rel="noreferrer">
          {t("settings.api.openapi")}
        </a>
      </Button>
    </Card>
  );
}
