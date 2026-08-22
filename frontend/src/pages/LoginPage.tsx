import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, type User } from "@/api/client";
import { AuthLayout } from "@/components/AuthLayout";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApiErrorMessage } from "@/useApiError";

export function LoginPage({ onLoggedIn }: { onLoggedIn: (user: User) => void }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLoggedIn(await api.login(username, password));
    } catch (cause) {
      setError(describe(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title={t("login.title")} subtitle={t("app.tagline")}>
      <form className="grid gap-4" onSubmit={submit}>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Field label={t("login.username")}>
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

        <Field label={t("login.password")}>
          {(id) => (
            <Input
              id={id}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          )}
        </Field>

        <Button type="submit" size="lg" className="mt-2" disabled={busy}>
          {t("login.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
