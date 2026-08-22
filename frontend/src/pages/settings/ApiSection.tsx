import { Check, Copy, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type ApiTokenSummary, type CreatedApiToken } from "@/api/client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiErrorMessage } from "@/useApiError";

export function ApiSection() {
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
    </div>
  );
}
