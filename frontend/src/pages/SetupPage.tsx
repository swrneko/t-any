import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, type User } from "@/api/client";
import { AuthLayout } from "@/components/AuthLayout";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApiErrorMessage } from "@/useApiError";

const MIN_PASSWORD_LENGTH = 8;

export function SetupPage({ onCreated }: { onCreated: (user: User) => void }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = confirmation.length > 0 && confirmation !== password;
  const canSubmit =
    username.length >= 3 && password.length >= MIN_PASSWORD_LENGTH && !mismatch && !busy;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.createFirstAdmin(username, password));
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title={t("setup.title")} subtitle={t("setup.subtitle")}>
      <form className="grid gap-4" onSubmit={submit}>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Field label={t("setup.username")}>
          {(id) => (
            <Input
              id={id}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoFocus
              required
            />
          )}
        </Field>

        <Field label={t("setup.password")} hint={t("setup.passwordHint")}>
          {(id) => (
            <Input
              id={id}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              required
            />
          )}
        </Field>

        <Field
          label={t("setup.confirm")}
          invalid={mismatch}
          hint={mismatch ? t("setup.passwordsDiffer") : ""}
        >
          {(id) => (
            <Input
              id={id}
              type="password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              aria-invalid={mismatch}
              autoComplete="new-password"
              required
            />
          )}
        </Field>

        <Button type="submit" size="lg" className="mt-2" disabled={!canSubmit}>
          {t("setup.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
