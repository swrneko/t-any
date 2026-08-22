import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type Retention, type Storage } from "@/api/client";
import { formatBytes } from "@/components/JobList";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiErrorMessage } from "@/useApiError";

const KEEP_FOREVER = "";

export function StorageSection() {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();

  const [storage, setStorage] = useState<Storage | null>(null);
  const [policy, setPolicy] = useState<Retention | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.readStorage().then(setStorage).catch(() => undefined);
    void api.readRetention().then(setPolicy).catch(() => undefined);
  }, []);

  const save = async () => {
    if (!policy) return;
    setError(null);
    try {
      setPolicy(await api.writeRetention(policy));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (cause) {
      setError(describe(cause));
    }
  };

  // An empty field means "keep it", which is the only value that can be typed
  // by deleting rather than by choosing a number.
  const days = (value: number | null) => (value === null ? KEEP_FOREVER : String(value));
  const parse = (value: string) => (value.trim() === "" ? null : Math.max(1, Number(value)));

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{t("settings.sections.storage")}</h2>
        <p className="text-sm text-muted-foreground">{t("settings.storage.explanation")}</p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {storage && (
        <Card className="grid gap-1 p-4">
          <p className="text-sm">
            {t("settings.storage.audio", { size: formatBytes(storage.audio_bytes) })}
          </p>
          <p className="text-sm text-muted-foreground">
            {t("settings.storage.other", {
              size: formatBytes(storage.other_bytes),
              n: storage.recordings,
            })}
          </p>
        </Card>
      )}

      {policy && (
        <>
          <Field label={t("settings.storage.audioDays")} hint={t("settings.storage.audioHint")}>
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                value={days(policy.audio_days)}
                placeholder={t("settings.storage.keep")}
                onChange={(event) =>
                  setPolicy({ ...policy, audio_days: parse(event.target.value) })
                }
              />
            )}
          </Field>

          <Field label={t("settings.storage.jobDays")} hint={t("settings.storage.jobHint")}>
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                value={days(policy.job_days)}
                placeholder={t("settings.storage.keep")}
                onChange={(event) => setPolicy({ ...policy, job_days: parse(event.target.value) })}
              />
            )}
          </Field>

          <div className="flex items-center gap-3">
            <Button onClick={() => void save()}>{t("presets.save")}</Button>
            {saved && <span className="text-sm text-success">{t("settings.storage.saved")}</span>}
          </div>

          {policy.job_days !== null && (
            <Alert variant="warning">
              <AlertDescription>
                {t("settings.storage.warning", { days: policy.job_days })}
              </AlertDescription>
            </Alert>
          )}
        </>
      )}
    </div>
  );
}
