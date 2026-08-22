import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type Provider } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

/** Read-only for now: the endpoints that would change a provider do not exist
 *  yet. What the API already exposes is shown as it is, masked key included. */
export function ProvidersSection() {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<Provider[] | null>(null);

  useEffect(() => {
    api
      .listProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          {t("settings.sections.providers")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("settings.providers.explanation")}</p>
      </div>

      {providers !== null &&
        (providers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("settings.providers.empty")}</p>
        ) : (
          <Card className="gap-0 overflow-hidden p-0">
            {providers.map((provider, index) => (
              <div
                key={provider.id}
                className={`grid gap-1 px-4 py-3 ${index > 0 ? "border-t border-border" : ""}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{provider.name}</span>
                  <Badge variant="outline">{t(`settings.providers.kind.${provider.kind}`)}</Badge>
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
            ))}
          </Card>
        ))}

      {/* Deleting every provider and restarting brings them back from the
          environment. That is the recovery path, but it looks like a ghost
          unless it is written down. */}
      <p className="text-sm text-muted-foreground">{t("settings.providers.seeding")}</p>
    </div>
  );
}
