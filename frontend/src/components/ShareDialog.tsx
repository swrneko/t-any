import { Check, Copy, Link2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, type Share } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApiErrorMessage } from "@/useApiError";

const LIFETIMES = ["forever", "7", "30"] as const;

export function ShareDialog({ jobId }: { jobId: string }) {
  const { t, i18n } = useTranslation();
  const describe = useApiErrorMessage();

  const [open, setOpen] = useState(false);
  const [share, setShare] = useState<Share | null>(null);
  const [lifetime, setLifetime] = useState<string>("forever");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .readShare(jobId)
      // A transcript that is not shared is the normal case, not a failure.
      .then(setShare)
      .catch(() => setShare(null));
  }, [open, jobId]);

  const link = share ? `${window.location.origin}/s/${share.token}` : "";

  const publish = async () => {
    setError(null);
    try {
      setShare(await api.createShare(jobId, lifetime === "forever" ? null : Number(lifetime)));
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const revoke = async () => {
    setError(null);
    try {
      await api.revokeShare(jobId);
      setShare(null);
    } catch (cause) {
      setError(describe(cause));
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Link2 className="size-4" />
          {t("share.title")}
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("share.title")}</DialogTitle>
          <DialogDescription>{t("share.explanation")}</DialogDescription>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {share === null ? (
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="share-lifetime">{t("share.lifetime")}</Label>
              <Select value={lifetime} onValueChange={setLifetime}>
                <SelectTrigger id="share-lifetime" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LIFETIMES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`share.lifetimes.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={() => void publish()}>{t("share.create")}</Button>
          </div>
        ) : (
          <div className="grid gap-4">
            <div className="flex gap-2">
              <Input readOnly value={link} onFocus={(event) => event.target.select()} />
              <Button variant="outline" size="icon" aria-label={t("share.copy")} onClick={() => void copy()}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              </Button>
            </div>

            <p className="text-sm text-muted-foreground">
              {share.expires_at
                ? t("share.expiresOn", {
                    date: new Date(share.expires_at).toLocaleDateString(i18n.language),
                  })
                : t("share.noExpiry")}
            </p>

            <Button variant="ghost" className="justify-self-start text-destructive" onClick={() => void revoke()}>
              <Trash2 className="size-4" />
              {t("share.revoke")}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
