import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError, type AuthMode, type User, type UserRow } from "@/api/client";
import { Field } from "@/components/Field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useApiErrorMessage } from "@/useApiError";

interface Doomed {
  user: UserRow;
  /** Set once the server has said how much would go with them. */
  jobs: number | null;
}

export function UsersSection({ me, authMode }: { me: User; authMode: AuthMode }) {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();

  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [adding, setAdding] = useState<{ username: string; password: string } | null>(null);
  const [doomed, setDoomed] = useState<Doomed | null>(null);
  const [resetting, setResetting] = useState<{ user: UserRow; password: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const local = authMode === "builtin";

  const refresh = useCallback(async () => {
    if (!me.is_admin) return;
    setUsers(await api.listUsers().catch(() => []));
  }, [me.is_admin]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const guard = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      await refresh();
      return true;
    } catch (cause) {
      setError(describe(cause));
      return false;
    }
  };

  const remove = async (target: Doomed) => {
    setError(null);
    try {
      await api.deleteUser(target.user.id, target.jobs !== null);
      setDoomed(null);
      await refresh();
    } catch (cause) {
      // The first refusal is not a failure but a question: it carries how many
      // recordings would go, which is what the confirmation needs to say.
      if (cause instanceof ApiError && cause.code === "user_has_jobs") {
        setDoomed({ ...target, jobs: Number(cause.params.jobs ?? 0) });
        return;
      }
      setError(describe(cause));
      setDoomed(null);
    }
  };

  return (
    <div className="grid gap-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{t("settings.sections.users")}</h2>
        <p className="text-sm text-muted-foreground">
          {local ? t("settings.users.explanation") : t("settings.users.external")}
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {local && <OwnPassword />}

      {me.is_admin && users !== null && (
        <>
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-medium">{t("settings.users.everyone")}</h3>
            {local && (
              <Button size="sm" onClick={() => setAdding({ username: "", password: "" })}>
                <Plus className="size-4" />
                {t("settings.users.new")}
              </Button>
            )}
          </div>

          <Card className="gap-0 overflow-hidden p-0">
            {users.map((user, index) => (
              <div
                key={user.id}
                className={`flex items-center gap-3 px-4 py-3 ${index > 0 ? "border-t border-border" : ""}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{user.username}</span>
                    {user.id === me.id && (
                      <Badge variant="outline">{t("settings.users.you")}</Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {t("settings.users.holds", { n: user.jobs })}
                  </p>
                </div>

                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  {t("settings.users.admin")}
                  <Switch
                    checked={user.is_admin}
                    aria-label={t("settings.users.admin")}
                    onCheckedChange={(checked) =>
                      void guard(() => api.updateUser(user.id, { is_admin: checked }))
                    }
                  />
                </label>

                {local && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("settings.users.resetPassword")}
                    title={t("settings.users.resetPassword")}
                    onClick={() => setResetting({ user, password: "" })}
                  >
                    <KeyRound className="size-4" />
                  </Button>
                )}

                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("settings.users.delete")}
                  disabled={user.id === me.id}
                  onClick={() => setDoomed({ user, jobs: null })}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </Card>
        </>
      )}

      <Dialog open={adding !== null} onOpenChange={(open) => !open && setAdding(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.users.new")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <Field label={t("setup.username")}>
              {(id) => (
                <Input
                  id={id}
                  autoComplete="off"
                  value={adding?.username ?? ""}
                  onChange={(event) =>
                    setAdding((current) =>
                      current ? { ...current, username: event.target.value } : current,
                    )
                  }
                />
              )}
            </Field>
            <Field label={t("setup.password")} hint={t("setup.passwordHint")}>
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="new-password"
                  value={adding?.password ?? ""}
                  onChange={(event) =>
                    setAdding((current) =>
                      current ? { ...current, password: event.target.value } : current,
                    )
                  }
                />
              )}
            </Field>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAdding(null)}>
              {t("presets.cancel")}
            </Button>
            <Button
              disabled={(adding?.password.length ?? 0) < 8 || (adding?.username.length ?? 0) < 3}
              onClick={() =>
                void guard(() => api.createUser(adding!.username, adding!.password)).then(
                  (ok) => ok && setAdding(null),
                )
              }
            >
              {t("presets.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={resetting !== null} onOpenChange={(open) => !open && setResetting(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.users.resetPassword")}</DialogTitle>
            <DialogDescription>
              {t("settings.users.resetFor", { name: resetting?.user.username ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <Field label={t("setup.password")} hint={t("setup.passwordHint")}>
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                value={resetting?.password ?? ""}
                onChange={(event) =>
                  setResetting((current) =>
                    current ? { ...current, password: event.target.value } : current,
                  )
                }
              />
            )}
          </Field>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setResetting(null)}>
              {t("presets.cancel")}
            </Button>
            <Button
              disabled={(resetting?.password.length ?? 0) < 8}
              onClick={() =>
                void guard(() =>
                  api.updateUser(resetting!.user.id, { password: resetting!.password }),
                ).then((ok) => ok && setResetting(null))
              }
            >
              {t("presets.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={doomed !== null} onOpenChange={(open) => !open && setDoomed(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.users.delete")}</DialogTitle>
            <DialogDescription>
              {doomed?.jobs
                ? t("settings.users.confirmWithJobs", {
                    name: doomed.user.username,
                    n: doomed.jobs,
                  })
                : t("settings.users.confirm", { name: doomed?.user.username ?? "" })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDoomed(null)}>
              {t("presets.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => doomed && void remove(doomed)}>
              {t("settings.users.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Everybody has one of these, administrator or not. */
function OwnPassword() {
  const { t } = useTranslation();
  const describe = useApiErrorMessage();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } catch (cause) {
      setError(describe(cause));
    }
  };

  return (
    <Card className="grid gap-4 p-4">
      <h3 className="font-medium">{t("settings.users.myAccount")}</h3>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Field label={t("settings.users.currentPassword")}>
        {(id) => (
          <Input
            id={id}
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        )}
      </Field>
      <Field label={t("settings.users.newPassword")} hint={t("setup.passwordHint")}>
        {(id) => (
          <Input
            id={id}
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
        )}
      </Field>

      <div className="flex items-center gap-3">
        <Button disabled={current === "" || next.length < 8} onClick={() => void submit()}>
          {t("settings.users.changePassword")}
        </Button>
        {done && <span className="text-sm text-success">{t("settings.storage.saved")}</span>}
      </div>
    </Card>
  );
}
